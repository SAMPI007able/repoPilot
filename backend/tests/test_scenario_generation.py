import unittest

from app.models.code_models import (
    CodeClass,
    CodeMethod,
    GraphRelationship,
    ParsedFile,
    RepositoryMetadata,
    RepositoryStatistics,
)
from app.services.ai.provider import AIProvider
from app.services.ai.test_generation_capability import TestGenerationCapability
from app.services.context_builder_service import ContextBuilderService
from app.services.graph_services import GraphService
from app.services.prompt_builder_service import PromptBuilderService


class RecordingProvider(AIProvider):
    def __init__(self) -> None:
        self.prompt = ""

    def generate(self, prompt: str) -> str:
        self.prompt = prompt
        return "# Integration Test Plan\nGenerated"


class ScenarioGenerationTests(unittest.TestCase):
    def test_scenario_generation_selects_matching_and_connected_modules(self) -> None:
        metadata = RepositoryMetadata(
            repository="payments",
            statistics=RepositoryStatistics(files=3, typescript=3, javascript=0),
            testFramework="vitest",
            parsed_file_details=[
                ParsedFile(
                    path="src/payments/PaymentService.ts",
                    file="PaymentService.ts",
                    source_code="export class PaymentService { retryCharge() {} }",
                    classes=[CodeClass(name="PaymentService")],
                    functions=[CodeMethod(name="retryCharge")],
                ),
                ParsedFile(
                    path="src/ledger/LedgerGateway.ts",
                    file="LedgerGateway.ts",
                    source_code="export class LedgerGateway { recordCharge() {} }",
                    classes=[CodeClass(name="LedgerGateway")],
                ),
                ParsedFile(
                    path="src/profile/ProfileView.ts",
                    file="ProfileView.ts",
                    source_code="export class ProfileView {}",
                    classes=[CodeClass(name="ProfileView")],
                ),
            ],
            relationships=[
                GraphRelationship(
                    source="src/payments/PaymentService.ts",
                    target="src/ledger/LedgerGateway.ts",
                    module="../ledger/LedgerGateway",
                    kind="local",
                )
            ],
        )
        provider = RecordingProvider()
        capability = TestGenerationCapability(
            provider,
            ContextBuilderService(GraphService()),
            PromptBuilderService(),
        )

        prompt, markdown = capability.execute_scenario(
            metadata,
            "A customer retries a payment after a timeout and receives one charge",
            "integration",
        )

        self.assertEqual(markdown, "# Integration Test Plan\nGenerated")
        self.assertIn("A customer retries a payment after a timeout", prompt)
        self.assertIn("src/payments/PaymentService.ts", prompt)
        self.assertIn("src/ledger/LedgerGateway.ts", prompt)
        self.assertNotIn("src/profile/ProfileView.ts", prompt)
        self.assertIn("scenario-scoped, not file-scoped", prompt)


if __name__ == "__main__":
    unittest.main()
