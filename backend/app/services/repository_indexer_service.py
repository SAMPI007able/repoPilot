import json
import os
from concurrent.futures import Future, ThreadPoolExecutor
from collections.abc import Callable
from app.models.code_models import (
    DocumentationAsset,
    PackageIntelligence,
    ParsedFile,
    ParsedFileSummary,
    RepositoryMetadata,
    RepositoryStatistics,
)
from app.services.graph_services import GraphService
from app.services.parser_services import ParserService
from app.services.repository_services import RepositoryService


class RepositoryIndexerService:
    DOCUMENTATION_EXTENSIONS = {
        ".md", ".mdx", ".txt", ".json", ".yaml", ".yml", ".rst", ".xml", ".csv",
        ".pdf", ".docx", ".pptx",
    }

    def __init__(
        self,
        repository_service: RepositoryService,
        parser_service: ParserService,
        graph_service: GraphService,
    ) -> None:
        self.repository_service = repository_service
        self.parser_service = parser_service
        self.graph_service = graph_service

    def index_repository(
        self,
        repository_name: str,
        repo_path: str,
        uploaded_docs: list[DocumentationAsset] | None = None,
    ) -> RepositoryMetadata:
        scan_result = self.repository_service.scan_repository(repo_path)
        parsed_files = self.parser_service.parse_many(
            (file_info["absolute_path"], file_info["path"])
            for file_info in scan_result["files"]
        )
        self._attach_existing_tests(parsed_files)
        relationships = self.graph_service.build_relationships(parsed_files)
        package_info = self._load_package_intelligence(repo_path)
        documentation = self._load_documentation(repo_path)
        if uploaded_docs:
            uploaded_paths = {asset.path for asset in uploaded_docs}
            documentation = [asset for asset in documentation if asset.path not in uploaded_paths]
            documentation.extend(uploaded_docs)

        return RepositoryMetadata(
            repository=repository_name,
            statistics=RepositoryStatistics(**scan_result["stats"]),
            testFramework=package_info.testFramework if package_info else None,
            packageInfo=package_info,
            documentation=documentation,
            parsedFiles=[self._summarize_file(parsed_file) for parsed_file in parsed_files],
            parsed_file_details=parsed_files,
            relationships=relationships,
            repositoryFiles=scan_result.get("runtime_files", []),
        )

    def index_repository_parallel(
        self,
        repository_name: str,
        repo_path: str,
        uploaded_docs: list[DocumentationAsset] | None = None,
        progress: Callable[[str, str, str | None], None] | None = None,
        parse_workers: int = 3,
    ) -> RepositoryMetadata:
        """Index independent repository concerns concurrently and report real stage progress."""
        report = progress or (lambda _stage, _status, _detail=None: None)
        worker_count = max(1, parse_workers)

        def run_stage(stage_id: str, operation):
            report(stage_id, "running", None)
            try:
                result = operation()
            except Exception as exc:
                report(stage_id, "failed", str(exc))
                raise
            report(stage_id, "completed", None)
            return result

        with ThreadPoolExecutor(max_workers=worker_count + 3) as executor:
            scan_future = executor.submit(
                run_stage,
                "scan",
                lambda: self.repository_service.scan_repository(repo_path),
            )
            documentation_future = executor.submit(
                run_stage,
                "documentation",
                lambda: self._load_documentation(repo_path),
            )
            package_future = executor.submit(
                run_stage,
                "package",
                lambda: self._load_package_intelligence(repo_path),
            )

            scan_result = scan_future.result()
            indexed_files = scan_result["files"]
            active_parse_workers = min(worker_count, len(indexed_files))
            parse_futures: list[tuple[list[int], Future[list[ParsedFile]]]] = []

            if active_parse_workers:
                indexed_positions = list(range(len(indexed_files)))
                chunks = [
                    indexed_positions[worker_index::active_parse_workers]
                    for worker_index in range(active_parse_workers)
                ]
                for worker_index, positions in enumerate(chunks, start=1):
                    stage_id = f"parse_{worker_index}"
                    parse_futures.append(
                        (
                            positions,
                            executor.submit(
                                run_stage,
                                stage_id,
                                lambda positions=positions: self.parser_service.parse_many(
                                    (
                                        indexed_files[position]["absolute_path"],
                                        indexed_files[position]["path"],
                                    )
                                    for position in positions
                                ),
                            ),
                        )
                    )

            for worker_index in range(active_parse_workers + 1, worker_count + 1):
                report(f"parse_{worker_index}", "completed", "No additional parser batch required")

            parsed_by_position: dict[int, ParsedFile] = {}
            for positions, parse_future in parse_futures:
                parsed_chunk = parse_future.result()
                parsed_by_position.update(zip(positions, parsed_chunk))
            parsed_files = [parsed_by_position[position] for position in range(len(indexed_files))]

            documentation = documentation_future.result()
            package_info = package_future.result()

        self._attach_existing_tests(parsed_files)
        report("relationships", "running", None)
        try:
            relationships = self.graph_service.build_relationships(parsed_files)
        except Exception:
            report("relationships", "failed", None)
            raise
        report("relationships", "completed", None)

        if uploaded_docs:
            uploaded_paths = {asset.path for asset in uploaded_docs}
            documentation = [asset for asset in documentation if asset.path not in uploaded_paths]
            documentation.extend(uploaded_docs)

        report("finalize", "running", None)
        metadata = RepositoryMetadata(
            repository=repository_name,
            statistics=RepositoryStatistics(**scan_result["stats"]),
            testFramework=package_info.testFramework if package_info else None,
            packageInfo=package_info,
            documentation=documentation,
            parsedFiles=[self._summarize_file(parsed_file) for parsed_file in parsed_files],
            parsed_file_details=parsed_files,
            relationships=relationships,
            repositoryFiles=scan_result.get("runtime_files", []),
        )
        report("finalize", "completed", None)
        return metadata

    def _summarize_file(self, parsed_file: ParsedFile) -> ParsedFileSummary:
        return ParsedFileSummary(
            path=parsed_file.path,
            classes=len(parsed_file.classes),
            functions=len(parsed_file.functions),
            imports=len(parsed_file.imports),
            existing_tests=len(parsed_file.existing_tests),
            complexity=parsed_file.complexity,
        )

    def _attach_existing_tests(self, parsed_files: list[ParsedFile]) -> None:
        production_files = [parsed_file for parsed_file in parsed_files if not self._is_test_file(parsed_file.path)]
        test_files = [parsed_file for parsed_file in parsed_files if self._is_test_file(parsed_file.path)]

        for test_file in test_files:
            test_file.is_test_file = True

        tests_by_key: dict[str, list[str]] = {}
        for test_file in test_files:
            tests_by_key.setdefault(self._normalize_file_key(test_file.file), []).append(test_file.path)

        for production_file in production_files:
            production_file.existing_tests = tests_by_key.get(
                self._normalize_file_key(production_file.file),
                [],
            )

    def _normalize_file_key(self, file_name: str) -> str:
        normalized = file_name.lower()
        for marker in (".test.", ".spec."):
            normalized = normalized.replace(marker, ".")
        if normalized.startswith("test_"):
            normalized = normalized[5:]
        if normalized.endswith("_test.py"):
            normalized = normalized[:-8] + ".py"
        elif normalized.endswith("tests.java"):
            normalized = normalized[:-10] + ".java"
        elif normalized.endswith("test.java"):
            normalized = normalized[:-9] + ".java"
        return normalized

    def _is_test_file(self, path: str) -> bool:
        normalized = path.lower().replace("\\", "/")
        file_name = normalized.rsplit("/", 1)[-1]
        return (
            ".test." in normalized
            or ".spec." in normalized
            or "/tests/" in normalized
            or "/__tests__/" in normalized
            or "/src/test/" in normalized
            or file_name.startswith("test_")
            or file_name.endswith("_test.py")
            or file_name.endswith("test.java")
        )

    def _load_package_intelligence(self, repo_path: str) -> PackageIntelligence | None:
        package_json_path = os.path.join(repo_path, "package.json")
        if not os.path.isfile(package_json_path):
            return None

        with open(package_json_path, "r", encoding="utf-8") as package_file:
            package_json = json.load(package_file)

        dependencies = package_json.get("dependencies", {})
        dev_dependencies = package_json.get("devDependencies", {})
        scripts = package_json.get("scripts", {})
        combined_dependencies = {**dependencies, **dev_dependencies}

        return PackageIntelligence(
            testFramework=self._detect_test_framework(combined_dependencies),
            dependencies=dependencies,
            devDependencies=dev_dependencies,
            scripts=scripts,
            engines=package_json.get("engines", {}),
            typescriptVersion=combined_dependencies.get("typescript"),
            reactVersion=combined_dependencies.get("react"),
            vueVersion=combined_dependencies.get("vue"),
        )

    def _detect_test_framework(self, dependencies: dict[str, str]) -> str | None:
        framework_packages = [
            ("vitest", "vitest"),
            ("jest", "jest"),
            ("mocha", "mocha"),
            ("@playwright/test", "playwright"),
            ("cypress", "cypress"),
        ]

        for package_name, framework_name in framework_packages:
            if package_name in dependencies:
                return framework_name

        return None

    def _load_documentation(self, repo_path: str) -> list[DocumentationAsset]:
        documentation: list[DocumentationAsset] = []
        direct_files = ["README.md", "architecture.md", "CONTRIBUTING.md"]
        directory_prefixes = ["docs", "adr", "project_docs"]

        for file_name in direct_files:
            file_path = os.path.join(repo_path, file_name)
            if os.path.isfile(file_path):
                documentation.append(self._read_documentation_asset(repo_path, file_path))

        for directory_prefix in directory_prefixes:
            documentation_dir = os.path.join(repo_path, directory_prefix)
            if not os.path.isdir(documentation_dir):
                continue

            for root, dirs, files in os.walk(documentation_dir):
                dirs[:] = [
                    directory_name
                    for directory_name in dirs
                    if directory_name not in self.repository_service.IGNORE_DIRS
                ]
                for file_name in files:
                    if os.path.splitext(file_name)[1].lower() not in self.DOCUMENTATION_EXTENSIONS:
                        continue
                    file_path = os.path.join(root, file_name)
                    documentation.append(self._read_documentation_asset(repo_path, file_path))

        return documentation

    def _read_documentation_asset(self, repo_path: str, file_path: str) -> DocumentationAsset:
        extension = os.path.splitext(file_path)[1].lower()
        relative_path = os.path.relpath(file_path, repo_path).replace("\\", "/")
        if extension in {".pdf", ".docx", ".pptx"}:
            return DocumentationAsset(
                path=relative_path,
                source=f"[Document '{os.path.basename(file_path)}' is stored in the workspace; text extraction is not supported.]",
            )

        with open(file_path, "r", encoding="utf-8", errors="ignore") as documentation_file:
            source = documentation_file.read()

        return DocumentationAsset(
            path=relative_path,
            source=source,
        )
