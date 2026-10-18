import os

from app.services.ai.gemini_provider import GeminiProvider
from app.services.ai.openai_compatible_provider import (
    OpenAIProvider,
    OpenRouterProvider,
    QwenProvider,
)
from app.services.ai.provider import AIProvider


SUPPORTED_PROVIDERS = {"gemini", "openai", "openrouter", "qwen"}


def create_ai_provider(capability: str) -> AIProvider:
    """Create the configured provider for ``chat`` or ``generation``."""
    if capability not in {"chat", "generation"}:
        raise ValueError(f"Unsupported AI capability: {capability}")
    prefix = capability.upper()
    provider_name = (
        os.getenv(f"AI_{prefix}_PROVIDER", "").strip()
        or os.getenv("AI_PROVIDER", "gemini").strip()
        or "gemini"
    ).lower()
    if provider_name not in SUPPORTED_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_PROVIDERS))
        raise ValueError(f"AI provider must be one of: {supported}.")

    default_limit = "30000" if capability == "chat" else "60000"
    max_input_tokens = int(
        os.getenv(
            f"AI_{prefix}_MAX_INPUT_TOKENS",
            os.getenv(f"GEMINI_{prefix}_MAX_INPUT_TOKENS", default_limit),
        )
    )
    timeout_seconds = float(os.getenv("AI_PROVIDER_TIMEOUT_SECONDS", "120"))

    if provider_name == "gemini":
        default_thinking = "minimal" if capability == "chat" else "low"
        return GeminiProvider(
            model=os.getenv(f"GEMINI_{prefix}_MODEL") or os.getenv("GEMINI_MODEL"),
            thinking_level=os.getenv(
                f"GEMINI_{prefix}_THINKING_LEVEL", default_thinking
            ),
            max_input_tokens=max_input_tokens,
        )

    if provider_name == "openai":
        return OpenAIProvider(
            api_key=os.getenv("OPENAI_API_KEY"),
            model=os.getenv(f"OPENAI_{prefix}_MODEL")
            or os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
            reasoning_effort=os.getenv(
                f"OPENAI_{prefix}_REASONING_EFFORT",
                os.getenv("OPENAI_REASONING_EFFORT", "low"),
            ),
            max_input_tokens=max_input_tokens,
            timeout_seconds=timeout_seconds,
        )

    if provider_name == "openrouter":
        return OpenRouterProvider(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            model=os.getenv(f"OPENROUTER_{prefix}_MODEL")
            or os.getenv("OPENROUTER_MODEL", "qwen/qwen3.7-flash"),
            base_url=os.getenv(
                "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
            ).rstrip("/"),
            site_url=os.getenv("OPENROUTER_SITE_URL") or os.getenv("FRONTEND_URL"),
            app_name=os.getenv("OPENROUTER_APP_NAME", "TestForge"),
            max_input_tokens=max_input_tokens,
            timeout_seconds=timeout_seconds,
        )

    return QwenProvider(
        api_key=os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY"),
        model=os.getenv(f"QWEN_{prefix}_MODEL")
        or os.getenv("QWEN_MODEL", "qwen3.7-flash"),
        base_url=os.getenv(
            "QWEN_BASE_URL",
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        ).rstrip("/"),
        enable_thinking=_boolean_env(
            f"QWEN_{prefix}_ENABLE_THINKING",
            _boolean_env("QWEN_ENABLE_THINKING", False),
        ),
        max_input_tokens=max_input_tokens,
        timeout_seconds=timeout_seconds,
    )


def _boolean_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false.")
