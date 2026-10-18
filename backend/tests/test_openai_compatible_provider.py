import sys
import types
import unittest
from unittest.mock import patch

from app.services.ai.openai_compatible_provider import (
    OpenAIProvider,
    OpenRouterProvider,
    QwenProvider,
)
from app.services.ai.provider import AIProviderPromptTooLargeError, AIProviderQuotaError


class FakeRateLimitError(Exception):
    status_code = 429

    def __init__(self) -> None:
        super().__init__("429 rate limit; retry after 12.2s")
        self.response = types.SimpleNamespace(headers={"retry-after": "12.2"})


class FakeResponses:
    def __init__(self, outcome) -> None:
        self.outcome = outcome
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        if kwargs.get("stream"):
            return iter(self.outcome)
        return self.outcome


class FakeCompletions:
    def __init__(self, response, stream) -> None:
        self.response = response
        self.stream = stream
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return iter(self.stream) if kwargs.get("stream") else self.response


class OpenAICompatibleProviderTests(unittest.TestCase):
    @staticmethod
    def _sdk(client, captured_options: list[dict]):
        def create_client(**kwargs):
            captured_options.append(kwargs)
            return client

        module = types.SimpleNamespace(OpenAI=create_client)
        return patch.dict(sys.modules, {"openai": module})

    def test_openai_uses_responses_api_without_storage(self) -> None:
        responses = FakeResponses(types.SimpleNamespace(output_text="answer"))
        client = types.SimpleNamespace(responses=responses)
        options: list[dict] = []
        provider = OpenAIProvider(
            api_key="openai-key",
            model="gpt-5.6-luna",
            max_input_tokens=100,
            reasoning_effort="low",
        )

        with self._sdk(client, options):
            result = provider.generate("question")

        self.assertEqual(result, "answer")
        self.assertEqual(responses.calls[0]["model"], "gpt-5.6-luna")
        self.assertEqual(responses.calls[0]["reasoning"], {"effort": "low"})
        self.assertFalse(responses.calls[0]["store"])
        self.assertEqual(options[0]["max_retries"], 0)

    def test_openai_streams_only_output_text_deltas(self) -> None:
        responses = FakeResponses([
            types.SimpleNamespace(type="response.created"),
            types.SimpleNamespace(type="response.output_text.delta", delta="Hello"),
            types.SimpleNamespace(type="response.output_text.delta", delta=" world"),
        ])
        provider = OpenAIProvider(
            api_key="openai-key", model="gpt-5.6-luna", max_input_tokens=100
        )

        with self._sdk(types.SimpleNamespace(responses=responses), []):
            result = list(provider.stream("question"))

        self.assertEqual(result, ["Hello", " world"])

    def test_qwen_uses_configured_compatible_endpoint_and_streams(self) -> None:
        response = types.SimpleNamespace(choices=[types.SimpleNamespace(
            message=types.SimpleNamespace(content="answer")
        )])
        chunks = [types.SimpleNamespace(choices=[types.SimpleNamespace(
            delta=types.SimpleNamespace(content="chunk")
        )])]
        completions = FakeCompletions(response, chunks)
        client = types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=completions)
        )
        options: list[dict] = []
        provider = QwenProvider(
            api_key="qwen-key",
            model="qwen3.7-flash",
            base_url="https://workspace.example/compatible-mode/v1",
            max_input_tokens=100,
            enable_thinking=False,
        )

        with self._sdk(client, options):
            self.assertEqual(provider.generate("question"), "answer")
            self.assertEqual(list(provider.stream("question")), ["chunk"])

        self.assertEqual(options[0]["base_url"], "https://workspace.example/compatible-mode/v1")
        self.assertEqual(
            completions.calls[0]["extra_body"], {"enable_thinking": False}
        )
        self.assertEqual(
            completions.calls[1]["stream_options"], {"include_usage": True}
        )

    def test_rate_limit_opens_cooldown_without_sdk_retry(self) -> None:
        responses = FakeResponses(FakeRateLimitError())
        provider = OpenAIProvider(
            api_key="openai-key", model="gpt-5.6-luna", max_input_tokens=100
        )

        with self._sdk(types.SimpleNamespace(responses=responses), []):
            with self.assertRaises(AIProviderQuotaError) as raised:
                provider.generate("question")
            with self.assertRaises(AIProviderQuotaError):
                provider.generate("question")

        self.assertEqual(raised.exception.provider, "OpenAI")
        self.assertEqual(raised.exception.retry_after_seconds, 13)
        self.assertEqual(len(responses.calls), 1)

    def test_openrouter_uses_its_key_endpoint_and_qwen_slug(self) -> None:
        response = types.SimpleNamespace(choices=[types.SimpleNamespace(
            message=types.SimpleNamespace(content="routed answer")
        )])
        completions = FakeCompletions(response, [])
        client = types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=completions)
        )
        options: list[dict] = []
        provider = OpenRouterProvider(
            api_key="sk-or-test",
            model="qwen/qwen3.7-flash",
            base_url="https://openrouter.ai/api/v1",
            max_input_tokens=100,
            site_url="https://app.example.test",
        )

        with self._sdk(client, options):
            result = provider.generate("question")

        self.assertEqual(result, "routed answer")
        self.assertEqual(options[0]["api_key"], "sk-or-test")
        self.assertEqual(options[0]["base_url"], "https://openrouter.ai/api/v1")
        self.assertEqual(options[0]["default_headers"]["X-Title"], "TestForge")
        self.assertEqual(
            options[0]["default_headers"]["HTTP-Referer"],
            "https://app.example.test",
        )
        self.assertEqual(completions.calls[0]["model"], "qwen/qwen3.7-flash")
        self.assertNotIn("extra_body", completions.calls[0])

    def test_rejects_estimated_oversized_prompt_before_network(self) -> None:
        provider = QwenProvider(
            api_key="qwen-key",
            model="qwen3.7-flash",
            base_url="https://workspace.example/compatible-mode/v1",
            max_input_tokens=2,
        )
        with self.assertRaises(AIProviderPromptTooLargeError):
            provider.generate("1234567")


if __name__ == "__main__":
    unittest.main()
