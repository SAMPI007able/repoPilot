import os


def infer_repository_root(file_path: str, relative_path: str) -> str:
    repository_root = os.path.abspath(file_path)
    for _ in relative_path.replace("\\", "/").split("/"):
        repository_root = os.path.dirname(repository_root)
    return repository_root


def to_posix_relative(repository_root: str, candidate: str) -> str:
    return os.path.relpath(candidate, repository_root).replace("\\", "/")


def is_within_repository(repository_root: str, candidate: str) -> bool:
    try:
        relative = os.path.relpath(candidate, repository_root)
    except ValueError:
        return False
    return relative != "" and not relative.startswith("..") and not os.path.isabs(relative)


def first_existing_source(repository_root: str, candidates: list[str]) -> str | None:
    for candidate in candidates:
        if (
            os.path.isfile(candidate)
            and is_within_repository(repository_root, candidate)
        ):
            return to_posix_relative(repository_root, candidate)
    return None


def python_module_candidates(base_path: str) -> list[str]:
    return [f"{base_path}.py", os.path.join(base_path, "__init__.py")]


def java_type_candidates(base_path: str) -> list[str]:
    return [f"{base_path}.java"]


def search_roots_for(file_path: str, repository_root: str) -> list[str]:
    roots: list[str] = []
    current = os.path.dirname(os.path.abspath(file_path))
    repository_root = os.path.abspath(repository_root)
    while True:
        roots.append(current)
        if os.path.normcase(current) == os.path.normcase(repository_root):
            break
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return roots
