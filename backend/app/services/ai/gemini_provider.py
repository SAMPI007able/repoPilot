import logging
import math
import os
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


class GeminiProvider(AIProvider):
    RETRYABLE_STATUS_CODES = {408, 500, 502, 503, 504}
    THINKING_LEVELS = {"minimal", "low", "medium", "high"}
    DEFAULT_QUOTA_RETRY_SECONDS = 60

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        fallback_models: list[str] | None = None,
        thinking_level: str | None = None,
        max_input_tokens: int | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        if fallback_models is None:
            configured_fallbacks = os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.1-flash-lite")
            fallback_models = [name.strip() for name in configured_fallbacks.split(",") if name.strip()]
        self.fallback_models = [name for name in fallback_models if name != self.model]
        self.thinking_level = (
            thinking_level or os.getenv("GEMINI_THINKING_LEVEL", "medium")
        ).strip().lower()
        if self.thinking_level not in self.THINKING_LEVELS:
            raise ValueError(
                "Gemini thinking level must be one of: minimal, low, medium, high."
            )
        self.max_input_tokens = max_input_tokens or int(
            os.getenv("GEMINI_MAX_INPUT_TOKENS", "30000")
        )
        if self.max_input_tokens <= 0:
            raise ValueError("Gemini maximum input tokens must be greater than zero.")
        self._client = None
        self._quota_blocked_until: dict[str, float] = {}

    def generate(self, prompt: str) -> str:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured.")

        client = self._get_client()
        models = [self.model, *self.fallback_models]
        last_error: Exception | None = None

        for attempt, model_name in enumerate(models, start=1):
            self._raise_if_quota_blocked(model_name)
            try:
                self._validate_prompt_size(client, model_name, prompt)
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=self._generation_config(),
                )
            except Exception as exc:
                if self._is_quota_error(exc):
                    self._log_attempt_failure(model_name, attempt, exc, False)
                    raise self._quota_error(model_name, exc) from exc
                retryable = self._is_retryable(exc)
                self._log_attempt_failure(model_name, attempt, exc, retryable)
                if not retryable:
                    raise
                last_error = exc
                continue

            if not getattr(response, "text", None):
                raise RuntimeError(f"Gemini model '{model_name}' returned an empty response.")

            return response.text

        attempted_models = ", ".join(models)
        raise AIProviderUnavailableError(
            f"Gemini is temporarily unavailable after trying: {attempted_models}. Please try again later."
        ) from last_error

    def stream(self, prompt: str) -> Iterator[str]:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured.")

        client = self._get_client()
        models = [self.model, *self.fallback_models]
        last_error: Exception | None = None

        for attempt, model_name in enumerate(models, start=1):
            self._raise_if_quota_blocked(model_name)
            emitted = False
            try:
                self._validate_prompt_size(client, model_name, prompt)
                for chunk in client.models.generate_content_stream(
                    model=model_name,
                    contents=prompt,
                    config=self._generation_config(),
                ):
                    text = getattr(chunk, "text", None)
                    if text:
                        emitted = True
                        yield text
            except Exception as exc:
                # Once text has reached the client, falling back would duplicate or
                # contradict the partial answer. Surface the interruption instead.
                if self._is_quota_error(exc):
                    self._log_attempt_failure(
                        model_name, attempt, exc, False, streaming=True, emitted=emitted,
                    )
                    raise self._quota_error(model_name, exc) from exc
                retryable = self._is_retryable(exc)
                will_retry = retryable and not emitted
                self._log_attempt_failure(
                    model_name,
                    attempt,
                    exc,
                    retryable,
                    streaming=True,
                    emitted=emitted,
                )
                if not will_retry:
                    raise
                last_error = exc
                continue

            if emitted:
                return
            raise RuntimeError(f"Gemini model '{model_name}' returned an empty response.")

        attempted_models = ", ".join(models)
        raise AIProviderUnavailableError(
            f"Gemini is temporarily unavailable after trying: {attempted_models}. Please try again later."
        ) from last_error

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError(
                "google-genai is not installed. Add it to the backend environment to use Gemini."
            ) from exc
        # The application owns model fallback behavior. Disable the SDK's default
        # 429/5xx retries so one request cannot silently multiply quota usage.
        self._client = genai.Client(
            api_key=self.api_key,
            http_options={"retry_options": {"attempts": 1}},
        )
        return self._client

    def _validate_prompt_size(self, client, model_name: str, prompt: str) -> None:
        response = client.models.count_tokens(model=model_name, contents=prompt)
        input_tokens = int(getattr(response, "total_tokens", 0))
        logger.info(
            "Gemini prompt measured: model=%s input_tokens=%d max_input_tokens=%d",
            model_name,
            input_tokens,
            self.max_input_tokens,
        )
        if input_tokens > self.max_input_tokens:
            raise AIProviderPromptTooLargeError(input_tokens, self.max_input_tokens)

    def _raise_if_quota_blocked(self, model_name: str) -> None:
        remaining = self._quota_blocked_until.get(model_name, 0) - time.monotonic()
        if remaining > 0:
            raise AIProviderQuotaError(model_name, math.ceil(remaining), provider="Gemini")

    def _quota_error(self, model_name: str, error: Exception) -> AIProviderQuotaError:
        retry_after = self._retry_after_seconds(error)
        self._quota_blocked_until[model_name] = time.monotonic() + retry_after
        return AIProviderQuotaError(model_name, retry_after, provider="Gemini")

    def _retry_after_seconds(self, error: Exception) -> int:
        details = getattr(error, "details", None)
        if isinstance(details, dict):
            details = details.get("error", details).get("details", [])
        if isinstance(details, list):
            for detail in details:
                if not isinstance(detail, dict):
                    continue
                if str(detail.get("@type", "")).endswith("RetryInfo"):
                    match = re.search(r"([\d.]+)s", str(detail.get("retryDelay", "")))
                    if match:
                        return max(1, math.ceil(float(match.group(1))))
        match = re.search(r"retry(?:\s+in|Delay['\": ]+)\s*([\d.]+)s", str(error), re.I)
        if match:
            return max(1, math.ceil(float(match.group(1))))
        return self.DEFAULT_QUOTA_RETRY_SECONDS

    def _generation_config(self) -> dict:
        return {"thinking_config": {"thinking_level": self.thinking_level}}

    def _log_attempt_failure(
        self,
        model_name: str,
        attempt: int,
        error: Exception,
        retryable: bool,
        *,
        streaming: bool = False,
        emitted: bool = False,
    ) -> None:
        code = getattr(error, "code", None)
        status = getattr(error, "status", None)
        status_code = getattr(error, "status_code", None)
        error_message = str(error)
        if self.api_key:
            error_message = error_message.replace(self.api_key, "[REDACTED]")

        logger.warning(
            "Gemini model request failed: model=%s attempt=%d streaming=%s "
            "retryable=%s partial_response_emitted=%s error_type=%s "
            "error_code=%s error_status=%s http_status=%s error=%s",
            model_name,
            attempt,
            streaming,
            retryable,
            emitted,
            type(error).__name__,
            code,
            status,
            status_code,
            error_message[:2000],
            extra={
                "geminiModel": model_name,
                "attempt": attempt,
                "streaming": streaming,
                "retryable": retryable,
                "partialResponseEmitted": emitted,
                "errorType": type(error).__name__,
                "errorCode": str(code) if code is not None else None,
                "errorStatus": str(status) if status is not None else None,
                "httpStatus": str(status_code) if status_code is not None else None,
                "errorMessage": error_message[:2000],
            },
        )

    def _is_retryable(self, error: Exception) -> bool:
        code = getattr(error, "code", None)
        if hasattr(code, "value"):
            code = code.value
        try:
            if int(code) in self.RETRYABLE_STATUS_CODES:
                return True
        except (TypeError, ValueError):
            pass

        match = re.match(r"^\s*(\d{3})\b", str(error))
        return bool(match and int(match.group(1)) in self.RETRYABLE_STATUS_CODES)

    def _is_quota_error(self, error: Exception) -> bool:
        code = getattr(error, "code", None)
        if hasattr(code, "value"):
            code = code.value
        try:
            if int(code) == 429:
                return True
        except (TypeError, ValueError):
            pass
        return bool(re.match(r"^\s*429\b", str(error)))
