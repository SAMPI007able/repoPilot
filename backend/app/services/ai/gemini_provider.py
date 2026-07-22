import os
import re

from app.services.ai.provider import AIProvider, AIProviderUnavailableError


class GeminiProvider(AIProvider):
    RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        fallback_models: list[str] | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        if fallback_models is None:
            configured_fallbacks = os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.1-flash-lite")
            fallback_models = [name.strip() for name in configured_fallbacks.split(",") if name.strip()]
        self.fallback_models = [name for name in fallback_models if name != self.model]

    def generate(self, prompt: str) -> str:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured.")

        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError(
                "google-genai is not installed. Add it to the backend environment to use Gemini."
            ) from exc

        client = genai.Client(api_key=self.api_key)
        models = [self.model, *self.fallback_models]
        last_error: Exception | None = None

        for model_name in models:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
            except Exception as exc:
                if not self._is_retryable(exc):
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
