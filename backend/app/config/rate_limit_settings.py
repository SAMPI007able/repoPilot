from dataclasses import dataclass
import os


@dataclass(frozen=True)
class RateLimitPolicy:
    limit: int
    window_seconds: int


@dataclass(frozen=True)
class RateLimitSettings:
    enabled: bool
    environment: str
    redis_url: str
    policies: dict[str, RateLimitPolicy]
    active_previews_per_user: int
    active_browser_sessions_per_user: int
    concurrency_ttl_seconds: int

    @classmethod
    def from_env(cls) -> "RateLimitSettings":
        environment = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "production")).lower()
        requested_enabled = _boolean("RATE_LIMIT_ENABLED", True)
        if not requested_enabled and environment not in {"development", "local", "test"}:
            raise ValueError("RATE_LIMIT_ENABLED=false is only permitted in development, local, or test environments.")
        default_window = _positive_int("RATE_LIMIT_WINDOW_SECONDS", 86_400)

        def policy(action: str, variable: str, default: int) -> tuple[str, RateLimitPolicy]:
            return action, RateLimitPolicy(
                limit=_positive_int(variable, default),
                window_seconds=_positive_int(f"{variable}_WINDOW_SECONDS", default_window),
            )

        policies = dict([
            policy("repository_index", "RATE_LIMIT_REPOSITORY_INDEX_DAILY", 5),
            policy("ai_generation", "RATE_LIMIT_AI_GENERATION_DAILY", 30),
            policy("project_chat", "RATE_LIMIT_PROJECT_CHAT_DAILY", 60),
            policy("document_upload", "RATE_LIMIT_DOCUMENT_UPLOAD_DAILY", 10),
            policy("preview_creation", "RATE_LIMIT_PREVIEW_CREATION_DAILY", 5),
            policy("preview_extension", "RATE_LIMIT_PREVIEW_EXTENSION_DAILY", 20),
            policy("browser_session_creation", "RATE_LIMIT_BROWSER_SESSION_DAILY", 20),
            policy("screenshot_generation", "RATE_LIMIT_SCREENSHOT_DAILY", 50),
            policy("support_ticket", "RATE_LIMIT_SUPPORT_TICKET_DAILY", 10),
        ])
        return cls(
            enabled=requested_enabled,
            environment=environment,
            redis_url=os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"),
            policies=policies,
            active_previews_per_user=_positive_int("CONCURRENCY_LIMIT_PREVIEWS_PER_USER", 1),
            active_browser_sessions_per_user=_positive_int("CONCURRENCY_LIMIT_BROWSER_SESSIONS_PER_USER", 1),
            concurrency_ttl_seconds=_positive_int("CONCURRENCY_LIMIT_TTL_SECONDS", 172_800),
        )


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    return value


def _boolean(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    if value.lower() not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false.")
    return value.lower() == "true"
