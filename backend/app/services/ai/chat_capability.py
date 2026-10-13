from app.models.code_models import RepositoryMetadata
from collections.abc import Iterator
from app.services.ai.ai_capability import AICapability
from app.services.ai.provider import AIProvider
from app.services.chat_prompt_builder_service import ChatPromptBuilderService


class ChatCapability(AICapability):
    def __init__(
        self,
        provider: AIProvider,
        prompt_builder: ChatPromptBuilderService,
    ) -> None:
        self.provider = provider
        self.prompt_builder = prompt_builder

    def execute(
        self,
        repository_metadata: RepositoryMetadata,
        query: str,
        history: list[tuple[str, str]] | None = None,
    ) -> tuple[str, str]:
        prompt = self.prompt_builder.build_prompt(
            query=query, repository_metadata=repository_metadata, history=history,
        )
        return prompt, self.provider.generate(prompt)

    def stream(
        self,
        repository_metadata: RepositoryMetadata,
        query: str,
        history: list[tuple[str, str]] | None = None,
    ) -> tuple[str, Iterator[str]]:
        prompt = self.prompt_builder.build_prompt(
            query=query, repository_metadata=repository_metadata, history=history,
        )
        return prompt, self.provider.stream(prompt)
