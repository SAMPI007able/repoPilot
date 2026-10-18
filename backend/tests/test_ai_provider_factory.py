import os
import unittest
from unittest.mock import patch

from app.services.ai.openai_compatible_provider import (
    OpenAIProvider,
    OpenRouterProvider,
    QwenProvider,
)
from app.services.ai.provider_factory import create_ai_provider


class AIProviderFactoryTests(unittest.TestCase):
    def test_selects_openai_for_both_capabilities(self) -> None:
        with patch.dict(os.environ, {
            "AI_PROVIDER": "openai",
            "OPENAI_API_KEY": "configured",
            "OPENAI_MODEL": "gpt-5.6-luna",
        }, clear=True):
            provider = create_ai_provider("chat")

        self.assertIsInstance(provider, OpenAIProvider)
        self.assertEqual(provider.model, "gpt-5.6-luna")
        self.assertEqual(provider.max_input_tokens, 30_000)

    def test_capability_override_can_select_qwen(self) -> None:
        with patch.dict(os.environ, {
            "AI_PROVIDER": "openai",
            "AI_CHAT_PROVIDER": "qwen",
            "QWEN_API_KEY": "configured",
            "QWEN_MODEL": "qwen3.7-flash",
            "QWEN_BASE_URL": "https://workspace.example/compatible-mode/v1",
        }, clear=True):
            provider = create_ai_provider("chat")

        self.assertIsInstance(provider, QwenProvider)
        self.assertEqual(provider.model, "qwen3.7-flash")
        self.assertEqual(
            provider.base_url, "https://workspace.example/compatible-mode/v1"
        )

    def test_blank_capability_override_uses_default_provider(self) -> None:
        with patch.dict(os.environ, {
            "AI_PROVIDER": "openai",
            "AI_CHAT_PROVIDER": "",
            "OPENAI_API_KEY": "configured",
        }, clear=True):
            provider = create_ai_provider("chat")

        self.assertIsInstance(provider, OpenAIProvider)

    def test_selects_openrouter_qwen_slug(self) -> None:
        with patch.dict(os.environ, {
            "AI_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "sk-or-test",
        }, clear=True):
            provider = create_ai_provider("chat")

        self.assertIsInstance(provider, OpenRouterProvider)
        self.assertEqual(provider.model, "qwen/qwen3.7-flash")
        self.assertEqual(provider.base_url, "https://openrouter.ai/api/v1")


if __name__ == "__main__":
    unittest.main()
