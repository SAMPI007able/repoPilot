from app.models.code_models import RepositoryMetadata
from app.services.ai.ai_capability import AICapability
from app.services.ai.provider import AIProvider
from app.services.context_builder_service import ContextBuilderService
from app.services.prompt_builder_service import PromptBuilderService


class TestGenerationCapability(AICapability):
    def __init__(
        self,
        provider: AIProvider,
        context_builder: ContextBuilderService,
        prompt_builder: PromptBuilderService,
    ) -> None:
        self.provider = provider
        self.context_builder = context_builder
        self.prompt_builder = prompt_builder

    def execute(
        self,
        repository_metadata: RepositoryMetadata,
        target: str,
        test_type: str,
    ) -> tuple[str, str]:
        prompt = self.prepare(repository_metadata, target, test_type)
        return prompt, self.generate_prepared(prompt)

    def prepare(
        self,
        repository_metadata: RepositoryMetadata,
        target: str,
        test_type: str,
    ) -> str:
        context = self.context_builder.build_context(
            repository_metadata=repository_metadata,
            target=target,
            test_type=test_type,
        )
        return self.prompt_builder.build_prompt(context)

    def execute_scenario(
        self,
        repository_metadata: RepositoryMetadata,
        scenario: str,
        test_type: str,
    ) -> tuple[str, str]:
        prompt = self.prepare_scenario(repository_metadata, scenario, test_type)
        return prompt, self.generate_prepared(prompt)

    def prepare_scenario(
        self,
        repository_metadata: RepositoryMetadata,
        scenario: str,
        test_type: str,
    ) -> str:
        context = self.context_builder.build_scenario_context(
            repository_metadata=repository_metadata,
            scenario=scenario,
            test_type=test_type,
        )
        return self.prompt_builder.build_scenario_prompt(context)

    def generate_prepared(self, prompt: str) -> str:
        return self.provider.generate(prompt)
