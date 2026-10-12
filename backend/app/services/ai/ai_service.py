from app.services.ai.chat_capability import ChatCapability
from app.services.ai.documentation_capability import DocumentationCapability
from app.services.ai.test_generation_capability import TestGenerationCapability


class AIService:
    def __init__(
        self,
        chat_capability: ChatCapability,
        test_generation_capability: TestGenerationCapability,
        documentation_capability: DocumentationCapability,
    ) -> None:
        self.chat_capability = chat_capability
        self.test_generation_capability = test_generation_capability
        self.documentation_capability = documentation_capability

    def chat(
        self,
        repository_metadata,
        query: str,
        history: list[tuple[str, str]] | None = None,
    ) -> tuple[str, str]:
        return self.chat_capability.execute(repository_metadata, query, history)

    def generate_tests(self, repository_metadata, target: str, test_type: str) -> tuple[str, str]:
        return self.test_generation_capability.execute(repository_metadata, target, test_type)

    def generate_tests_from_scenario(
        self,
        repository_metadata,
        scenario: str,
        test_type: str,
    ) -> tuple[str, str]:
        return self.test_generation_capability.execute_scenario(
            repository_metadata,
            scenario,
            test_type,
        )

    def documentation_query(self, repository_metadata, query: str) -> tuple[str, str]:
        return self.documentation_capability.execute(repository_metadata, query)
