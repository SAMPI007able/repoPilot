import logging
import os
import re
from collections.abc import Iterator

from app.services.ai.provider import AIProvider, AIProviderUnavailableError


logger = logging.getLogger(__name__)


class GeminiProvider(AIProvider):
    RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
    THINKING_LEVELS = {"minimal", "low", "medium", "high"}

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        fallback_models: list[str] | None = None,
        thinking_level: str | None = None,
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
        self._client = None

    def generate(self, prompt: str) -> str:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured.")

        client = self._get_client()
        models = [self.model, *self.fallback_models]
        last_error: Exception | None = None

        for attempt, model_name in enumerate(models, start=1):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=self._generation_config(),
                )
            except Exception as exc:
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
            emitted = False
            try:
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
        self._client = genai.Client(api_key=self.api_key)
        return self._client

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
