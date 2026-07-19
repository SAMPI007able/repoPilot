from app.models.code_models import ParsedFile, ParsedFileSummary, RepositoryMetadata, RepositoryStatistics
from app.services.parser_services import ParserService
from app.services.repository_services import RepositoryService


class RepositoryIndexerService:
    def __init__(
        self,
        repository_service: RepositoryService,
        parser_service: ParserService,
    ) -> None:
        self.repository_service = repository_service
        self.parser_service = parser_service

    def index_repository(self, repository_name: str, repo_path: str) -> RepositoryMetadata:
        scan_result = self.repository_service.scan_repository(repo_path)
        parsed_files = [
            self.parser_service.parse(file_info["absolute_path"], file_info["path"])
            for file_info in scan_result["files"]
        ]

        return RepositoryMetadata(
            repository=repository_name,
            statistics=RepositoryStatistics(**scan_result["stats"]),
            parsedFiles=[self._summarize_file(parsed_file) for parsed_file in parsed_files],
        )

    def _summarize_file(self, parsed_file: ParsedFile) -> ParsedFileSummary:
        return ParsedFileSummary(
            path=parsed_file.path,
            classes=len(parsed_file.classes),
            functions=len(parsed_file.functions),
            imports=len(parsed_file.imports),
        )
