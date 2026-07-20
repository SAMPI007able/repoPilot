from app.models.code_models import DependencySummary, GenerationContext, ParsedFile, RepositoryMetadata
from app.services.graph_services import GraphService


class ContextBuilderService:
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
