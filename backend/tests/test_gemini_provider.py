import sys
import types
import unittest
from unittest.mock import patch

from app.services.ai.gemini_provider import GeminiProvider
from app.services.ai.provider import AIProviderUnavailableError


class FakeGeminiError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"{code} UNAVAILABLE")
        self.code = code


class FakeModels:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []
        self.configs: list[dict] = []

    def generate_content(self, model: str, contents: str, config: dict) -> object:
        del contents
        self.calls.append(model)
        self.configs.append(config)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def generate_content_stream(self, model: str, contents: str, config: dict):
        del contents
        self.calls.append(model)
        self.configs.append(config)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        yield from outcome


class GeminiProviderTests(unittest.TestCase):
    def _install_fake_sdk(self, models: FakeModels):
        fake_genai = types.SimpleNamespace(Client=lambda api_key: types.SimpleNamespace(models=models))
        fake_google = types.ModuleType("google")
        fake_google.genai = fake_genai
        return patch.dict(sys.modules, {"google": fake_google, "google.genai": fake_genai})

    def test_uses_fallback_model_after_retryable_capacity_error(self) -> None:
        models = FakeModels([FakeGeminiError(503), types.SimpleNamespace(text="generated tests")])
        provider = GeminiProvider(
            api_key="test-key",
            model="gemini-3.5-flash",
            fallback_models=["gemini-3.1-flash-lite"],
        )

        with self._install_fake_sdk(models):
            result = provider.generate("prompt")

        self.assertEqual(result, "generated tests")
        self.assertEqual(models.calls, ["gemini-3.5-flash", "gemini-3.1-flash-lite"])

    def test_applies_configured_thinking_level(self) -> None:
        models = FakeModels([types.SimpleNamespace(text="answer")])
        provider = GeminiProvider(api_key="test-key", thinking_level="minimal", fallback_models=[])

        with self._install_fake_sdk(models):
            provider.generate("prompt")

        self.assertEqual(
            models.configs,
            [{"thinking_config": {"thinking_level": "minimal"}}],
        )

    def test_streams_chunks_with_configured_thinking_level(self) -> None:
        models = FakeModels([[
            types.SimpleNamespace(text="Hello"),
            types.SimpleNamespace(text=" world"),
        ]])
        provider = GeminiProvider(api_key="test-key", thinking_level="low", fallback_models=[])

        with self._install_fake_sdk(models):
            result = list(provider.stream("prompt"))

        self.assertEqual(result, ["Hello", " world"])
        self.assertEqual(models.configs[0]["thinking_config"]["thinking_level"], "low")

    def test_does_not_fallback_for_non_retryable_request_error(self) -> None:
        models = FakeModels([FakeGeminiError(400)])
        provider = GeminiProvider(api_key="test-key", fallback_models=["gemini-3.1-flash-lite"])

        with self._install_fake_sdk(models), self.assertRaises(FakeGeminiError):
            provider.generate("prompt")

        self.assertEqual(models.calls, ["gemini-3.5-flash"])

    def test_reports_unavailable_after_all_models_fail(self) -> None:
        models = FakeModels([FakeGeminiError(503), FakeGeminiError(503)])
        provider = GeminiProvider(api_key="test-key", fallback_models=["gemini-3.1-flash-lite"])

        with self._install_fake_sdk(models), self.assertRaises(AIProviderUnavailableError):
            provider.generate("prompt")


if __name__ == "__main__":
    unittest.main()
