import json
import os
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
    def __init__(
        self,
        repository_service: RepositoryService,
        parser_service: ParserService,
        graph_service: GraphService,
    ) -> None:
        self.repository_service = repository_service
        self.parser_service = parser_service
        self.graph_service = graph_service

    def index_repository(self, repository_name: str, repo_path: str) -> RepositoryMetadata:
        scan_result = self.repository_service.scan_repository(repo_path)
        parsed_files = [
            self.parser_service.parse(file_info["absolute_path"], file_info["path"])
            for file_info in scan_result["files"]
        ]
        self._attach_existing_tests(parsed_files)
        relationships = self.graph_service.build_relationships(parsed_files)
        package_info = self._load_package_intelligence(repo_path)
        documentation = self._load_documentation(repo_path)

        return RepositoryMetadata(
            repository=repository_name,
            statistics=RepositoryStatistics(**scan_result["stats"]),
            testFramework=package_info.testFramework if package_info else None,
            packageInfo=package_info,
            documentation=documentation,
            parsedFiles=[self._summarize_file(parsed_file) for parsed_file in parsed_files],
            parsed_file_details=parsed_files,
            relationships=relationships,
        )

    def _summarize_file(self, parsed_file: ParsedFile) -> ParsedFileSummary:
        return ParsedFileSummary(
            path=parsed_file.path,
            classes=len(parsed_file.classes),
            functions=len(parsed_file.functions),
            imports=len(parsed_file.imports),
            existing_tests=len(parsed_file.existing_tests),
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
        return normalized

    def _is_test_file(self, path: str) -> bool:
        normalized = path.lower()
        return (
            ".test." in normalized
            or ".spec." in normalized
            or "/tests/" in normalized
            or "/__tests__/" in normalized
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
        directory_prefixes = ["docs", "adr"]

        for file_name in direct_files:
            file_path = os.path.join(repo_path, file_name)
            if os.path.isfile(file_path):
                documentation.append(self._read_documentation_asset(repo_path, file_path))

        for root, _, files in os.walk(repo_path):
            relative_root = os.path.relpath(root, repo_path).replace("\\", "/").lower()
            if relative_root == ".":
                continue

            if not any(relative_root == prefix or relative_root.startswith(f"{prefix}/") for prefix in directory_prefixes):
                continue

            for file_name in files:
                file_path = os.path.join(root, file_name)
                documentation.append(self._read_documentation_asset(repo_path, file_path))

        return documentation

    def _read_documentation_asset(self, repo_path: str, file_path: str) -> DocumentationAsset:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as documentation_file:
            source = documentation_file.read()

        return DocumentationAsset(
            path=os.path.relpath(file_path, repo_path).replace("\\", "/"),
            source=source,
        )
