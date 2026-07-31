import re

from app.models.code_models import DependencySummary, GenerationContext, ParsedFile, RepositoryMetadata
from app.services.graph_services import GraphService


class ContextBuilderService:
    SCENARIO_STOP_WORDS = {
        "about", "after", "against", "before", "being", "could", "does",
        "from", "have", "into", "multiple", "should", "that", "their",
        "then", "there", "these", "they", "this", "through", "together",
        "verify", "want", "when", "where", "which", "with", "without",
    }

    def __init__(self, graph_service: GraphService) -> None:
        self.graph_service = graph_service

    def build_context(
        self,
        repository_metadata: RepositoryMetadata,
        target: str,
        test_type: str,
    ) -> GenerationContext:
        target_file = self._find_target_file(repository_metadata.parsed_file_details, target)
        if target_file is None:
            raise ValueError(f"Could not find target '{target}' in repository metadata.")

        outgoing_relationships = self.graph_service.get_outgoing_relationships(
            repository_metadata.relationships,
            target_file.path,
        )
        related_files = self._collect_related_files(
            repository_metadata.parsed_file_details,
            outgoing_relationships,
        )
        dependency_summaries = [
            self._build_dependency_summary(target_file, related_file)
            for related_file in related_files
        ]

        return GenerationContext(
            target=target,
            test_type=test_type,
            target_source=target_file.source_code,
            classes=target_file.classes,
            imports=target_file.imports,
            methods=target_file.functions,
            dependencies=dependency_summaries,
            existing_tests=target_file.existing_tests,
            test_framework=repository_metadata.testFramework,
            package_info=repository_metadata.packageInfo,
            documentation=repository_metadata.documentation,
        )

    def build_scenario_context(
        self,
        repository_metadata: RepositoryMetadata,
        scenario: str,
        test_type: str,
    ) -> GenerationContext:
        selected_files, matched_terms_by_path = self._select_scenario_files(
            repository_metadata,
            scenario,
        )
        relevant_modules = [
            DependencySummary(
                name=parsed_file.classes[0].name if parsed_file.classes else parsed_file.file,
                reason=self._scenario_file_reason(
                    parsed_file.path,
                    matched_terms_by_path,
                ),
                source=self._truncate_source(parsed_file.source_code),
                path=parsed_file.path,
            )
            for parsed_file in selected_files
        ]

        return GenerationContext(
            target="End-to-end scenario",
            test_type=test_type,
            target_source="",
            scenario=scenario,
            classes=[code_class for file in selected_files for code_class in file.classes],
            imports=[import_reference for file in selected_files for import_reference in file.imports],
            methods=[method for file in selected_files for method in file.functions],
            dependencies=relevant_modules,
            existing_tests=list(
                dict.fromkeys(
                    test_path
                    for file in selected_files
                    for test_path in file.existing_tests
                )
            ),
            test_framework=repository_metadata.testFramework,
            package_info=repository_metadata.packageInfo,
            documentation=repository_metadata.documentation,
        )

    def _select_scenario_files(
        self,
        repository_metadata: RepositoryMetadata,
        scenario: str,
    ) -> tuple[list[ParsedFile], dict[str, list[str]]]:
        source_files = [
            parsed_file
            for parsed_file in repository_metadata.parsed_file_details
            if not self._is_test_file(parsed_file.path)
        ]
        terms = self._scenario_terms(scenario)
        scored_files: list[tuple[int, ParsedFile, list[str]]] = []

        for parsed_file in source_files:
            path_text = parsed_file.path.lower()
            symbol_text = " ".join(
                [
                    *(code_class.name.lower() for code_class in parsed_file.classes),
                    *(method.name.lower() for method in parsed_file.functions),
                ]
            )
            source_text = parsed_file.source_code[:16000].lower()
            matched_terms: list[str] = []
            score = 0
            for term in terms:
                variants = {term, term.removesuffix("s")}
                if any(variant and variant in path_text for variant in variants):
                    score += 8
                    matched_terms.append(term)
                elif any(variant and variant in symbol_text for variant in variants):
                    score += 5
                    matched_terms.append(term)
                elif any(variant and variant in source_text for variant in variants):
                    score += 1
                    matched_terms.append(term)
            if score:
                scored_files.append((score, parsed_file, list(dict.fromkeys(matched_terms))))

        scored_files.sort(key=lambda item: (-item[0], item[1].path))
        seeds = [item[1] for item in scored_files[:4]]
        matched_terms_by_path = {item[1].path: item[2] for item in scored_files[:4]}

        if not seeds:
            degree_by_path: dict[str, int] = {}
            for relationship in repository_metadata.relationships:
                degree_by_path[relationship.source] = degree_by_path.get(relationship.source, 0) + 1
                degree_by_path[relationship.target] = degree_by_path.get(relationship.target, 0) + 1
            seeds = sorted(
                source_files,
                key=lambda file: (-degree_by_path.get(file.path, 0), file.path),
            )[:4]

        selected_by_path = {file.path: file for file in seeds}
        files_by_path = {file.path: file for file in source_files}
        seed_paths = set(selected_by_path)
        connected_paths: list[str] = []
        for relationship in repository_metadata.relationships:
            if relationship.source in seed_paths:
                connected_paths.append(relationship.target)
            if relationship.target in seed_paths:
                connected_paths.append(relationship.source)

        for path in connected_paths:
            if len(selected_by_path) >= 8:
                break
            connected_file = files_by_path.get(path)
            if connected_file is not None:
                selected_by_path.setdefault(path, connected_file)

        return list(selected_by_path.values()), matched_terms_by_path

    def _scenario_terms(self, scenario: str) -> list[str]:
        return list(
            dict.fromkeys(
                token
                for token in re.findall(r"[a-zA-Z0-9]+", scenario.lower())
                if len(token) >= 4 and token not in self.SCENARIO_STOP_WORDS
            )
        )

    def _scenario_file_reason(
        self,
        path: str,
        matched_terms_by_path: dict[str, list[str]],
    ) -> str:
        matched_terms = matched_terms_by_path.get(path)
        if matched_terms:
            return f"Matches scenario terms: {', '.join(matched_terms)}"
        return "Directly connected to a scenario-matched module"

    def _is_test_file(self, path: str) -> bool:
        normalized = path.lower()
        return (
            ".test." in normalized
            or ".spec." in normalized
            or "/tests/" in normalized
            or normalized.startswith("tests/")
        )

    def _truncate_source(self, source: str, limit: int = 8000) -> str:
        if len(source) <= limit:
            return source
        return f"{source[:limit]}\n// ... source truncated for scenario context"

    def _find_target_file(self, parsed_files: list[ParsedFile], target: str) -> ParsedFile | None:
        normalized_target = target.lower()

        for parsed_file in parsed_files:
            if parsed_file.file.lower() == normalized_target:
                return parsed_file

            file_stem = parsed_file.file.rsplit(".", 1)[0].lower()
            if file_stem == normalized_target:
                return parsed_file

            if any(code_class.name.lower() == normalized_target for code_class in parsed_file.classes):
                return parsed_file

        return None

    def _collect_related_files(
        self,
        parsed_files: list[ParsedFile],
        relationships: list,
    ) -> list[ParsedFile]:
        parsed_files_by_path = {parsed_file.path: parsed_file for parsed_file in parsed_files}
        related_files: list[ParsedFile] = []

        for relationship in relationships:
            related_file = parsed_files_by_path.get(relationship.target)
            if related_file is not None:
                related_files.append(related_file)

        return related_files

    def _build_dependency_summary(
        self,
        target_file: ParsedFile,
        dependency_file: ParsedFile,
    ) -> DependencySummary:
        dependency_name = dependency_file.classes[0].name if dependency_file.classes else dependency_file.file

        return DependencySummary(
            name=dependency_name,
            reason=f"Imported by {target_file.file.rsplit('.', 1)[0]}",
            source=dependency_file.source_code,
            path=dependency_file.path,
        )
