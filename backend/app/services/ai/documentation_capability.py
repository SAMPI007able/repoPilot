from app.models.code_models import RepositoryMetadata
from app.services.ai.ai_capability import AICapability
from app.services.ai.provider import AIProvider
from app.services.documentation_prompt_builder_service import DocumentationPromptBuilderService


class DocumentationCapability(AICapability):
    def __init__(
        self,
        provider: AIProvider,
        prompt_builder: DocumentationPromptBuilderService,
    ) -> None:
        self.provider = provider
        self.prompt_builder = prompt_builder

    def execute(self, repository_metadata: RepositoryMetadata, documentation_query: str) -> tuple[str, str]:
        prompt = self.prompt_builder.build_prompt(
            repository_metadata=repository_metadata,
            query=documentation_query,
        )
        return prompt, self.provider.generate(prompt)
