import unittest
from unittest.mock import patch

from app.models.code_models import (
    GraphRelationship,
    ParsedFileSummary,
    RepositoryMetadata,
    RepositoryStatistics,
)
from app.services.chat_prompt_builder_service import ChatPromptBuilderService


class ChatPromptBuilderServiceTests(unittest.TestCase):
    def test_prompt_is_bounded_and_query_relevant(self) -> None:
        metadata = RepositoryMetadata(
            repository="example/repository",
            statistics=RepositoryStatistics(
                files=20, typescript=20, javascript=0, python=0, java=0
            ),
            parsedFiles=[
                ParsedFileSummary(
                    path=f"src/module-{index}.ts",
                    classes=1,
                    functions=2,
                    imports=3,
                    existing_tests=0,
                    complexity=index + 1,
                )
                for index in range(19)
            ] + [
                ParsedFileSummary(
                    path="src/payments/checkout.ts",
                    classes=1,
                    functions=4,
                    imports=5,
                    existing_tests=1,
                    complexity=2,
                )
            ],
            relationships=[
                GraphRelationship(
                    source=f"src/module-{index}.ts",
                    target=f"src/module-{index + 1}.ts",
                    module=f"./module-{index + 1}",
                    kind="import",
                )
                for index in range(10)
            ],
        )
        environment = {
            "GEMINI_CHAT_MAX_INPUT_TOKENS": "1000",
            "GEMINI_CHAT_MAX_FILES": "3",
            "GEMINI_CHAT_MAX_RELATIONSHIPS": "2",
        }

        with patch.dict("os.environ", environment):
            prompt = ChatPromptBuilderService().build_prompt(
                "How does checkout process payments?", metadata
            )

        self.assertLessEqual(len(prompt), 3000)
        self.assertIn("src/payments/checkout.ts", prompt)
        self.assertIn("additional files omitted by relevance limit", prompt)
        self.assertIn("complexity", prompt)


if __name__ == "__main__":
    unittest.main()
