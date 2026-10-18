import logging
import math
import re
import time
from collections.abc import Iterator

from app.services.ai.provider import (
    AIProvider,
    AIProviderPromptTooLargeError,
    AIProviderQuotaError,
    AIProviderUnavailableError,
)


logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(AIProvider):
    """Shared provider for OpenAI and OpenAI-compatible chat APIs."""

    RETRYABLE_STATUS_CODES = {408, 500, 502, 503, 504}
    DEFAULT_QUOTA_RETRY_SECONDS = 60

    def __init__(
        self,
        *,
        provider_name: str,
        api_key: str | None,
        model: str,
        max_input_tokens: int,
        base_url: str | None = None,
        reasoning_effort: str | None = None,
        enable_thinking: bool | None = None,
        use_responses_api: bool = False,
        timeout_seconds: float = 120,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.api_key = api_key
        self.model = model
        self.max_input_tokens = max_input_tokens
        self.base_url = base_url
        self.reasoning_effort = reasoning_effort
        self.enable_thinking = enable_thinking
        self.use_responses_api = use_responses_api
        self.timeout_seconds = timeout_seconds
        self.default_headers = default_headers or {}
        self._client = None
        self._quota_blocked_until = 0.0
        if self.max_input_tokens <= 0:
            raise ValueError("AI maximum input tokens must be greater than zero.")

    def generate(self, prompt: str) -> str:
        self._validate_request(prompt)
        try:
            if self.use_responses_api:
                response = self._get_client().responses.create(**self._responses_request(prompt))
                text = getattr(response, "output_text", None)
            else:
                response = self._get_client().chat.completions.create(
                    **self._chat_request(prompt)
                )
                choices = getattr(response, "choices", [])
                text = choices[0].message.content if choices else None
        except Exception as exc:
            translated = self._translate_error(exc)
            if translated is exc:
                raise
            raise translated from exc
        if not text:
            raise RuntimeError(
                f"{self.provider_name} model '{self.model}' returned an empty response."
            )
        return text

    def stream(self, prompt: str) -> Iterator[str]:
        self._validate_request(prompt)
        emitted = False
        try:
            if self.use_responses_api:
                stream = self._get_client().responses.create(
                    **self._responses_request(prompt), stream=True
                )
                for event in stream:
                    if getattr(event, "type", None) != "response.output_text.delta":
                        continue
                    text = getattr(event, "delta", None)
                    if text:
                        emitted = True
                        yield text
            else:
                stream = self._get_client().chat.completions.create(
                    **self._chat_request(prompt),
                    stream=True,
                    stream_options={"include_usage": True},
                )
                for chunk in stream:
                    choices = getattr(chunk, "choices", [])
                    text = choices[0].delta.content if choices else None
                    if text:
                        emitted = True
                        yield text
        except Exception as exc:
            translated = self._translate_error(exc)
            if translated is exc:
                raise
            raise translated from exc
        if not emitted:
            raise RuntimeError(
                f"{self.provider_name} model '{self.model}' returned an empty response."
            )

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self.api_key:
            variable = {
                "OpenAI": "OPENAI_API_KEY",
                "OpenRouter": "OPENROUTER_API_KEY",
                "Qwen": "QWEN_API_KEY",
            }.get(self.provider_name, "AI_API_KEY")
            raise ValueError(f"{variable} is not configured.")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "openai is not installed. Add it to the backend environment to use "
                f"{self.provider_name}."
            ) from exc
        options = {
            "api_key": self.api_key,
            "max_retries": 0,
            "timeout": self.timeout_seconds,
        }
        if self.base_url:
            options["base_url"] = self.base_url
        if self.default_headers:
            options["default_headers"] = self.default_headers
        self._client = OpenAI(**options)
        return self._client

    def _responses_request(self, prompt: str) -> dict:
        request = {"model": self.model, "input": prompt, "store": False}
        if self.reasoning_effort:
            request["reasoning"] = {"effort": self.reasoning_effort}
        return request

    def _chat_request(self, prompt: str) -> dict:
        request = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self.enable_thinking is not None:
            request["extra_body"] = {"enable_thinking": self.enable_thinking}
        return request

    def _validate_request(self, prompt: str) -> None:
        remaining = self._quota_blocked_until - time.monotonic()
        if remaining > 0:
            raise AIProviderQuotaError(
                self.model,
                math.ceil(remaining),
                provider=self.provider_name,
            )
        # Neither OpenAI Responses nor the Qwen-compatible endpoint exposes a
        # preflight tokenizer. Three characters/token is deliberately conservative.
        estimated_tokens = math.ceil(len(prompt) / 3)
        if estimated_tokens > self.max_input_tokens:
            raise AIProviderPromptTooLargeError(
                estimated_tokens, self.max_input_tokens
            )

    def _translate_error(self, error: Exception) -> Exception:
        status_code = self._status_code(error)
        self._log_failure(error, status_code)
        if status_code == 429:
            retry_after = self._retry_after_seconds(error)
            self._quota_blocked_until = time.monotonic() + retry_after
            return AIProviderQuotaError(
                self.model, retry_after, provider=self.provider_name
            )
        if status_code in self.RETRYABLE_STATUS_CODES or type(error).__name__ in {
            "APIConnectionError",
            "APITimeoutError",
        }:
            return AIProviderUnavailableError(
                f"{self.provider_name} is temporarily unavailable for model "
                f"'{self.model}'. Please try again later."
            )
        return error

    @staticmethod
    def _status_code(error: Exception) -> int | None:
        code = getattr(error, "status_code", None) or getattr(error, "code", None)
        try:
            return int(code)
        except (TypeError, ValueError):
            match = re.match(r"^\s*(\d{3})\b", str(error))
            return int(match.group(1)) if match else None

    def _retry_after_seconds(self, error: Exception) -> int:
        response = getattr(error, "response", None)
        headers = getattr(response, "headers", {}) if response is not None else {}
        retry_after = headers.get("retry-after") if hasattr(headers, "get") else None
        if retry_after:
            try:
                return max(1, math.ceil(float(retry_after)))
            except ValueError:
                pass
        match = re.search(r"retry(?:\s+after|\s+in)\s*([\d.]+)s", str(error), re.I)
        if match:
            return max(1, math.ceil(float(match.group(1))))
        return self.DEFAULT_QUOTA_RETRY_SECONDS

    def _log_failure(self, error: Exception, status_code: int | None) -> None:
        message = str(error)
        if self.api_key:
            message = message.replace(self.api_key, "[REDACTED]")
        logger.warning(
            "%s model request failed: model=%s status=%s error_type=%s error=%s",
            self.provider_name,
            self.model,
            status_code,
            type(error).__name__,
            message[:2000],
            extra={
                "aiProvider": self.provider_name,
                "aiModel": self.model,
                "httpStatus": str(status_code) if status_code is not None else None,
                "errorType": type(error).__name__,
                "errorMessage": message[:2000],
            },
        )


class OpenAIProvider(OpenAICompatibleProvider):
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        max_input_tokens: int,
        reasoning_effort: str = "low",
        timeout_seconds: float = 120,
    ) -> None:
        super().__init__(
            provider_name="OpenAI",
            api_key=api_key,
            model=model,
            max_input_tokens=max_input_tokens,
            reasoning_effort=reasoning_effort,
            use_responses_api=True,
            timeout_seconds=timeout_seconds,
        )


class QwenProvider(OpenAICompatibleProvider):
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        base_url: str,
        max_input_tokens: int,
        enable_thinking: bool = False,
        timeout_seconds: float = 120,
    ) -> None:
        super().__init__(
            provider_name="Qwen",
            api_key=api_key,
            model=model,
            base_url=base_url,
            max_input_tokens=max_input_tokens,
            enable_thinking=enable_thinking,
            use_responses_api=False,
            timeout_seconds=timeout_seconds,
        )


class OpenRouterProvider(OpenAICompatibleProvider):
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        base_url: str,
        max_input_tokens: int,
        site_url: str | None = None,
        app_name: str = "TestForge",
        timeout_seconds: float = 120,
    ) -> None:
        headers = {"X-Title": app_name}
        if site_url:
            headers["HTTP-Referer"] = site_url
        super().__init__(
            provider_name="OpenRouter",
            api_key=api_key,
            model=model,
            base_url=base_url,
            max_input_tokens=max_input_tokens,
            use_responses_api=False,
            timeout_seconds=timeout_seconds,
            default_headers=headers,
        )
