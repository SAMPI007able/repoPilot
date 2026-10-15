import ast
import os
import re

from app.services.source_resolution import (
    first_existing_source,
    infer_repository_root,
    python_module_candidates,
    search_roots_for,
)


_PYTHON_CLASS = re.compile(r"^[ \t]*class[ \t]+([A-Za-z_][\w]*)", re.MULTILINE)
_PYTHON_FUNCTION = re.compile(r"^[ \t]*(?:async[ \t]+)?def[ \t]+([A-Za-z_][\w]*)", re.MULTILINE)
_PYTHON_IMPORT = re.compile(
    r"^[ \t]*(?:from[ \t]+(\.*[\w.]*)[ \t]+import[ \t]+(.+)|import[ \t]+([^\n#]+))",
    re.MULTILINE,
)
_PYTHON_DECISION = re.compile(
    r"\b(?:if|elif|for|while|except|and|or|case|match)\b|\bif[ \t]+[^\n]+[ \t]else\b",
    re.MULTILINE,
)


def parse_python_file(file_path: str, relative_path: str, repository_root: str | None = None) -> dict:
    source = _read_source(file_path)
    repository_root = repository_root or infer_repository_root(file_path, relative_path)
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return _fallback_metadata(file_path, relative_path, source, repository_root)
    return _metadata_from_ast(file_path, relative_path, source, repository_root, tree)


def _read_source(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="replace") as source_file:
        return source_file.read()


def _metadata_from_ast(
    file_path: str,
    relative_path: str,
    source: str,
    repository_root: str,
    tree: ast.AST,
) -> dict:
    classes: list[str] = []
    functions: list[str] = []
    imports: list[dict] = []
    complexity = 1

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
            complexity += 1
        elif isinstance(node, ast.Lambda):
            complexity += 1
        elif isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp)):
            complexity += 1
        elif isinstance(node, ast.ExceptHandler):
            complexity += 1
        elif isinstance(node, ast.BoolOp):
            complexity += max(len(node.values) - 1, 0)
        elif isinstance(node, ast.comprehension):
            complexity += 1 + len(node.ifs)
        elif hasattr(ast, "Match") and isinstance(node, ast.Match):
            complexity += _match_complexity(node)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(_build_python_import(file_path, repository_root, alias.name, 0, alias.name))
        elif isinstance(node, ast.ImportFrom):
            imports.extend(_imports_from_import_from(file_path, repository_root, node))

    return _metadata(file_path, relative_path, source, classes, functions, imports, complexity)


def _match_complexity(node: ast.AST) -> int:
    increment = 0
    for case in getattr(node, "cases", []):
        pattern = getattr(case, "pattern", None)
        if pattern is not None and type(pattern).__name__ == "MatchAs" and getattr(pattern, "pattern", None) is None:
            continue
        increment += 1
    return increment


def _imports_from_import_from(file_path: str, repository_root: str, node: ast.ImportFrom) -> list[dict]:
    if node.module == "__future__":
        return []
    if node.module:
        module = f"{'.' * node.level}{node.module}"
        return [_build_python_import(file_path, repository_root, module, node.level, node.module)]

    imports = []
    for alias in node.names:
        if alias.name == "*":
            module = "." * node.level or "."
            imports.append(_build_python_import(file_path, repository_root, module, node.level, None))
            continue
        module = f"{'.' * node.level}{alias.name}"
        imports.append(_build_python_import(file_path, repository_root, module, node.level, alias.name))
    return imports


def _build_python_import(
    file_path: str,
    repository_root: str,
    module: str,
    level: int,
    absolute_name: str | None,
) -> dict:
    resolved = _resolve_python_import(file_path, repository_root, module, level, absolute_name)
    return {
        "module": module,
        "resolved": resolved,
        "kind": "local" if resolved or level > 0 or module.startswith(".") else "external",
    }


def _resolve_python_import(
    file_path: str,
    repository_root: str,
    module: str,
    level: int,
    absolute_name: str | None,
) -> str | None:
    if level > 0:
        current = os.path.dirname(os.path.abspath(file_path))
        for _ in range(level):
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
        if absolute_name:
            base = os.path.join(current, *absolute_name.split("."))
        else:
            base = current
        return first_existing_source(repository_root, python_module_candidates(base))

    dotted = (absolute_name or module).lstrip(".")
    if not dotted:
        return None
    parts = dotted.split(".")
    for root in search_roots_for(file_path, repository_root):
        resolved = first_existing_source(repository_root, python_module_candidates(os.path.join(root, *parts)))
        if resolved:
            return resolved
    return None


def _fallback_metadata(file_path: str, relative_path: str, source: str, repository_root: str) -> dict:
    classes = _PYTHON_CLASS.findall(source)
    functions = _PYTHON_FUNCTION.findall(source)
    imports = []
    for match in _PYTHON_IMPORT.finditer(source):
        from_module, from_names, import_names = match.groups()
        if from_module is not None:
            level = len(from_module) - len(from_module.lstrip("."))
            absolute_name = from_module.lstrip(".") or None
            if absolute_name == "__future__":
                continue
            if absolute_name:
                imports.append(_build_python_import(file_path, repository_root, from_module, level, absolute_name))
            else:
                for name in _split_import_names(from_names):
                    imports.append(
                        _build_python_import(file_path, repository_root, f"{'.' * level}{name}", level, name)
                    )
            continue
        for name in _split_import_names(import_names or ""):
            imports.append(_build_python_import(file_path, repository_root, name, 0, name))

    complexity = 1 + len(functions) + len(_PYTHON_DECISION.findall(source))
    return _metadata(file_path, relative_path, source, classes, functions, imports, max(complexity, 1))


def _split_import_names(raw_names: str) -> list[str]:
    names = []
    for part in raw_names.replace("(", " ").replace(")", " ").split(","):
        name = part.split(" as ")[0].strip()
        if name and name != "*":
            names.append(name)
    return names


def _metadata(
    file_path: str,
    relative_path: str,
    source: str,
    classes: list[str],
    functions: list[str],
    imports: list[dict],
    complexity: int,
) -> dict:
    return {
        "file": os.path.basename(file_path),
        "relative_path": relative_path,
        "source_code": source,
        "classes": classes,
        "functions": functions,
        "imports": imports,
        "complexity": max(int(complexity), 1),
    }
