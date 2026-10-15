import os
import re

from app.services.source_resolution import (
    first_existing_source,
    infer_repository_root,
    java_type_candidates,
    search_roots_for,
)


_JAVA_TYPE = re.compile(r"\b(?:class|interface|enum|record|@interface)\s+([A-Za-z_][\w$]*)")
_JAVA_IMPORT = re.compile(r"\bimport\s+(?:static\s+)?([\w.]+(?:\.\*)?)\s*;")
_JAVA_REQUIRES = re.compile(r"\brequires\s+(?:transitive\s+|static\s+)?([\w.]+)\s*;")
_JAVA_METHOD = re.compile(
    r"(?:(?:public|protected|private|static|final|native|synchronized|abstract|default|"
    r"strictfp|sealed|non-sealed|transient|volatile)\s+)*"
    r"(?:<[^;{}()]+>\s*)?"
    r"(?:[\w$.]+\s*(?:<[^;{}()]+>)?(?:\s*\[\s*\])*\s+)?"
    r"([A-Za-z_][\w$]*)\s*\([^;{}]*\)\s*(?:throws\s+[^{;]+)?\s*(?:\{|;)"
)
_JAVA_METHOD_KEYWORDS = {
    "if",
    "for",
    "while",
    "switch",
    "catch",
    "synchronized",
    "try",
    "return",
    "throw",
    "new",
    "assert",
    "else",
    "do",
    "case",
    "default",
    "record",
    "class",
    "interface",
    "enum",
    "module",
    "requires",
    "exports",
    "opens",
    "uses",
    "provides",
    "package",
    "import",
}
_JAVA_DECISION = re.compile(r"\b(?:if|for|while|catch|case)\b")
_JAVA_SHORT_CIRCUIT = re.compile(r"&&|\|\|")
_JAVA_TERNARY = re.compile(r"(?<!<)\?(?!>)")
_TYPE_PREFIX = re.compile(r"\b(?:class|interface|enum|record|@interface)\s+$")


def parse_java_file(file_path: str, relative_path: str, repository_root: str | None = None) -> dict:
    source = _read_source(file_path)
    repository_root = repository_root or infer_repository_root(file_path, relative_path)
    stripped = _strip_comments_and_literals(source)
    classes = _JAVA_TYPE.findall(stripped)
    functions = [
        match.group(1)
        for match in _JAVA_METHOD.finditer(stripped)
        if match.group(1) not in _JAVA_METHOD_KEYWORDS and not _TYPE_PREFIX.search(stripped[: match.start()])
    ]
    imports = [_build_java_import(file_path, repository_root, module) for module in _JAVA_IMPORT.findall(stripped)]
    imports.extend(
        {
            "module": module,
            "resolved": None,
            "kind": "external",
        }
        for module in _JAVA_REQUIRES.findall(stripped)
    )
    complexity = (
        1
        + len(functions)
        + len(_JAVA_DECISION.findall(stripped))
        + len(_JAVA_SHORT_CIRCUIT.findall(stripped))
        + len(_JAVA_TERNARY.findall(stripped))
    )
    return {
        "file": os.path.basename(file_path),
        "relative_path": relative_path,
        "source_code": source,
        "classes": classes,
        "functions": functions,
        "imports": imports,
        "complexity": max(complexity, 1),
    }


def _read_source(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="replace") as source_file:
        return source_file.read()


def _build_java_import(file_path: str, repository_root: str, module: str) -> dict:
    wildcard = module.endswith(".*")
    dotted = module[:-2] if wildcard else module
    resolved = None if wildcard else _resolve_java_import(file_path, repository_root, dotted)
    local_package = wildcard and _java_package_exists(file_path, repository_root, dotted)
    return {
        "module": module,
        "resolved": resolved,
        "kind": "local" if resolved or local_package else "external",
    }


def _resolve_java_import(file_path: str, repository_root: str, dotted: str) -> str | None:
    parts = dotted.split(".")
    while parts:
        for root in search_roots_for(file_path, repository_root):
            resolved = first_existing_source(
                repository_root,
                java_type_candidates(os.path.join(root, *parts)),
            )
            if resolved:
                return resolved
        parts = parts[:-1]
    return None


def _java_package_exists(file_path: str, repository_root: str, dotted: str) -> bool:
    parts = dotted.split(".")
    for root in search_roots_for(file_path, repository_root):
        directory = os.path.join(root, *parts)
        if os.path.isdir(directory) and any(name.endswith(".java") for name in os.listdir(directory)):
            return True
    return False


def _strip_comments_and_literals(source: str) -> str:
    output: list[str] = []
    index = 0
    length = len(source)
    while index < length:
        current = source[index]
        nxt = source[index + 1] if index + 1 < length else ""
        if current == "/" and nxt == "/":
            index = _skip_to(source, index + 2, "\n", output, keep_end=True)
            continue
        if current == "/" and nxt == "*":
            index = _skip_block_comment(source, index + 2, output)
            continue
        if current == '"' and source.startswith('"""', index):
            index = _skip_delimited(source, index + 3, '"""', output)
            continue
        if current in {'"', "'"}:
            index = _skip_quoted(source, index, current, output)
            continue
        output.append(current)
        index += 1
    return "".join(output)


def _skip_to(source: str, index: int, terminator: str, output: list[str], keep_end: bool) -> int:
    end = source.find(terminator, index)
    if end < 0:
        output.append(" " * (len(source) - index))
        return len(source)
    output.append(" " * (end - index))
    if keep_end:
        output.append(terminator)
        return end + len(terminator)
    output.append(" " * len(terminator))
    return end + len(terminator)


def _skip_block_comment(source: str, index: int, output: list[str]) -> int:
    end = source.find("*/", index)
    if end < 0:
        fragment = source[index:]
        output.append(_spaces_preserving_newlines(fragment))
        return len(source)
    output.append(_spaces_preserving_newlines(source[index:end]))
    output.append("  ")
    return end + 2


def _skip_delimited(source: str, index: int, terminator: str, output: list[str]) -> int:
    end = source.find(terminator, index)
    if end < 0:
        output.append(_spaces_preserving_newlines(source[index - 3 :]))
        return len(source)
    output.append(_spaces_preserving_newlines(source[index - 3 : end + len(terminator)]))
    return end + len(terminator)


def _skip_quoted(source: str, start: int, quote: str, output: list[str]) -> int:
    index = start + 1
    while index < len(source):
        current = source[index]
        if current == "\\":
            index += 2
            continue
        if current == quote:
            output.append(" " * (index + 1 - start))
            return index + 1
        if current == "\n":
            break
        index += 1
    output.append(_spaces_preserving_newlines(source[start:index]))
    return index


def _spaces_preserving_newlines(fragment: str) -> str:
    return "".join("\n" if char == "\n" else " " for char in fragment)
