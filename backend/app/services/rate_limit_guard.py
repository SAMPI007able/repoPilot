from dataclasses import dataclass
from datetime import datetime, timezone

from app.config.rate_limit_settings import RateLimitSettings
from app.models.identity_models import Principal
from app.models.rate_limit_models import ConcurrencyResult, RateLimitResult
from app.services.rate_limit_service import RateLimitBackendUnavailable, RateLimitService


class QuotaAPIError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str, details: dict, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers or {}


@dataclass(frozen=True)
class RateLimitDecision:
    result: RateLimitResult | None
    headers: dict[str, str]


class RateLimitGuard:
    MESSAGES = {
        "repository_index": "Daily repository-indexing limit reached.",
        "ai_generation": "Daily AI-generation limit reached.",
        "project_chat": "Daily project-chat limit reached.",
        "document_upload": "Daily document-upload limit reached.",
        "preview_creation": "Daily preview-creation limit reached.",
        "preview_extension": "Daily preview-extension limit reached.",
        "browser_session_creation": "Daily browser-session limit reached.",
        "screenshot_generation": "Daily screenshot-generation limit reached.",
        "email_verification": "Verification email limit reached. Please try again later.",
    }

    def __init__(self, service: RateLimitService, settings: RateLimitSettings) -> None:
        self.service = service
        self.settings = settings

    def enforce(self, principal: Principal, action: str, *, fail_closed: bool = False) -> RateLimitDecision:
        if not self.settings.enabled:
            return RateLimitDecision(None, {})
        policy = self.settings.policies[action]
        try:
            result = self.service.check_and_consume(principal.user_id, action, policy.limit, policy.window_seconds)
        except RateLimitBackendUnavailable:
            if fail_closed:
                raise QuotaAPIError(
                    503, "RATE_LIMIT_UNAVAILABLE", "The quota service is temporarily unavailable.",
                    {"action": action}, {"Retry-After": "30"},
                )
            return RateLimitDecision(None, {})
        headers = self._headers(result)
        if not result.allowed:
            raise QuotaAPIError(
                429, "RATE_LIMIT_EXCEEDED", self.MESSAGES[action],
                {
                    "action": action,
                    "limit": result.limit,
                    "current": result.current,
                    "remaining": result.remaining,
                    "resetAt": result.reset_at.isoformat().replace("+00:00", "Z"),
                },
                headers,
            )
        return RateLimitDecision(result, headers)

    def acquire(self, principal: Principal, resource: str, resource_id: str, *, fail_closed: bool = True) -> ConcurrencyResult:
        if not self.settings.enabled:
            return ConcurrencyResult(True, 0, 0)
        limit = (
            self.settings.active_previews_per_user
            if resource == "preview"
            else self.settings.active_browser_sessions_per_user
        )
        try:
            result = self.service.acquire_concurrency_slot(principal.user_id, resource, limit, resource_id)
        except RateLimitBackendUnavailable:
            if fail_closed:
                raise QuotaAPIError(
                    503, "RATE_LIMIT_UNAVAILABLE", "The resource quota service is temporarily unavailable.",
                    {"resource": resource}, {"Retry-After": "30"},
                )
            return ConcurrencyResult(True, limit, 0)
        if not result.allowed:
            label = "preview" if resource == "preview" else "browser session"
            raise QuotaAPIError(
                429, "CONCURRENCY_LIMIT_EXCEEDED", f"Only {limit} active {label}{'' if limit == 1 else 's'} allowed.",
                {"resource": resource, "limit": limit, "active": result.active},
                {"Retry-After": "30"},
            )
        return result

    @staticmethod
    def _headers(result: RateLimitResult) -> dict[str, str]:
        reset_epoch = int(result.reset_at.timestamp())
        retry_after = max(1, reset_epoch - int(datetime.now(timezone.utc).timestamp()))
        return {
            "X-RateLimit-Limit": str(result.limit),
            "X-RateLimit-Remaining": str(result.remaining),
            "X-RateLimit-Reset": str(reset_epoch),
            "Retry-After": str(retry_after),
        }
