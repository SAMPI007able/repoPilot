from app.models.code_models import (
    ImpactAnalysisResult,
    ImpactedComponent,
    ParsedFile,
    RepositoryMetadata,
)


class ImpactAnalysisService:
    def analyze(
        self,
        repository_metadata: RepositoryMetadata,
        target: str,
    ) -> ImpactAnalysisResult:
        target_file = self._find_target_file(repository_metadata.parsed_file_details, target)
        if target_file is None:
            raise ValueError(f"Could not find target '{target}' in repository metadata.")

        incoming_relationships = [
            relationship
            for relationship in repository_metadata.relationships
            if relationship.target == target_file.path
        ]
        outgoing_relationships = [
            relationship
            for relationship in repository_metadata.relationships
            if relationship.source == target_file.path
        ]

        parsed_files_by_path = {
            parsed_file.path: parsed_file
            for parsed_file in repository_metadata.parsed_file_details
        }
        affected_files = [
            parsed_files_by_path[relationship.source]
            for relationship in incoming_relationships
            if relationship.source in parsed_files_by_path
        ]

        affected_components = [
            ImpactedComponent(
                name=self._display_name(parsed_file),
                path=parsed_file.path,
                reason=f"Imports {self._display_name(target_file)}",
            )
            for parsed_file in affected_files
        ]

        potentially_affected_tests = self._collect_tests(target_file, affected_files)
        risk = self._calculate_risk(
            inbound_count=len(affected_files),
            outbound_count=len(outgoing_relationships),
            functions_count=len(target_file.functions),
            classes_count=len(target_file.classes),
            impacted_tests_count=len(potentially_affected_tests),
        )

        summary = self._build_summary(
            target_file=target_file,
            inbound_count=len(affected_files),
            outbound_count=len(outgoing_relationships),
            impacted_tests_count=len(potentially_affected_tests),
            risk=risk,
        )

        return ImpactAnalysisResult(
            workspaceId=repository_metadata.repository,
            target=target_file.path,
            affectedComponents=affected_components,
            potentiallyAffectedTests=potentially_affected_tests,
            risk=risk,
            summary=summary,
        )

    def _find_target_file(self, parsed_files: list[ParsedFile], target: str) -> ParsedFile | None:
        normalized_target = target.lower()

        for parsed_file in parsed_files:
            if parsed_file.path.lower() == normalized_target:
                return parsed_file

            if parsed_file.file.lower() == normalized_target:
                return parsed_file

            file_stem = parsed_file.file.rsplit(".", 1)[0].lower()
            if file_stem == normalized_target:
                return parsed_file

            if any(code_class.name.lower() == normalized_target for code_class in parsed_file.classes):
                return parsed_file

        return None

    def _collect_tests(
        self,
        target_file: ParsedFile,
        affected_files: list[ParsedFile],
    ) -> list[str]:
        tests: list[str] = []
        seen: set[str] = set()

        for file_path in [*target_file.existing_tests, *self._flatten_tests(affected_files)]:
            if file_path in seen:
                continue
            seen.add(file_path)
            tests.append(file_path)

        return tests

    def _flatten_tests(self, parsed_files: list[ParsedFile]) -> list[str]:
        flattened: list[str] = []
        for parsed_file in parsed_files:
            flattened.extend(parsed_file.existing_tests)
        return flattened

    def _calculate_risk(
        self,
        inbound_count: int,
        outbound_count: int,
        functions_count: int,
        classes_count: int,
        impacted_tests_count: int,
    ) -> str:
        score = inbound_count * 3 + outbound_count * 2 + functions_count + classes_count * 2
        if impacted_tests_count == 0:
            score += 4

        if score >= 12:
            return "high"
        if score >= 6:
            return "medium"
        return "low"

    def _build_summary(
        self,
        target_file: ParsedFile,
        inbound_count: int,
        outbound_count: int,
        impacted_tests_count: int,
        risk: str,
    ) -> str:
        return (
            f"{target_file.path} has {inbound_count} direct dependents and {outbound_count} outgoing dependencies. "
            f"{impacted_tests_count} existing tests intersect with this file's local blast radius. "
            f"Current change risk is {risk}."
        )

    def _display_name(self, parsed_file: ParsedFile) -> str:
        if parsed_file.classes:
            return parsed_file.classes[0].name

        return parsed_file.file.rsplit(".", 1)[0]
