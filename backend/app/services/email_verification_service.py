from dataclasses import dataclass
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


class EmailVerificationError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class Auth0VerificationSettings:
    enabled: bool
    issuer: str
    management_client_id: str
    management_client_secret: str
    application_client_id: str | None

    @classmethod
    def from_env(cls) -> "Auth0VerificationSettings":
        return cls(
            enabled=os.getenv("AUTH0_VERIFICATION_RESEND_ENABLED", "false").lower() == "true",
            issuer=os.getenv("OIDC_ISSUER", "").rstrip("/") + "/",
            management_client_id=os.getenv("AUTH0_MANAGEMENT_CLIENT_ID", ""),
            management_client_secret=os.getenv("AUTH0_MANAGEMENT_CLIENT_SECRET", ""),
            application_client_id=os.getenv("AUTH0_VERIFICATION_CLIENT_ID") or None,
        )


class Auth0EmailVerificationService:
    def __init__(self, settings: Auth0VerificationSettings) -> None:
        self.settings = settings
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0
        self._token_lock = threading.Lock()

    def send(self, subject: str) -> None:
        self._validate_configuration()
        payload: dict[str, str] = {"user_id": subject}
        if self.settings.application_client_id:
            payload["client_id"] = self.settings.application_client_id
        request = urllib.request.Request(
            urllib.parse.urljoin(self.settings.issuer, "api/v2/jobs/verification-email"),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._management_token()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10):
                return
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise EmailVerificationError(
                    429,
                    "VERIFICATION_EMAIL_PROVIDER_RATE_LIMITED",
                    "Auth0 is temporarily limiting verification emails. Please try again later.",
                    retryable=True,
                ) from exc
            raise EmailVerificationError(
                502,
                "VERIFICATION_EMAIL_SEND_FAILED",
                "The verification email could not be sent. Please try again later.",
                retryable=exc.code >= 500,
            ) from exc
        except (TimeoutError, urllib.error.URLError) as exc:
            raise EmailVerificationError(
                503,
                "VERIFICATION_EMAIL_PROVIDER_UNAVAILABLE",
                "The verification-email service is temporarily unavailable.",
                retryable=True,
            ) from exc

    def _management_token(self) -> str:
        with self._token_lock:
            if self._access_token and time.monotonic() < self._access_token_expires_at:
                return self._access_token
            request = urllib.request.Request(
                urllib.parse.urljoin(self.settings.issuer, "oauth/token"),
                data=json.dumps({
                    "client_id": self.settings.management_client_id,
                    "client_secret": self.settings.management_client_secret,
                    "audience": urllib.parse.urljoin(self.settings.issuer, "api/v2/"),
                    "grant_type": "client_credentials",
                }).encode("utf-8"),
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except (ValueError, TimeoutError, urllib.error.HTTPError, urllib.error.URLError) as exc:
                raise EmailVerificationError(
                    503,
                    "VERIFICATION_EMAIL_AUTH_FAILED",
                    "Verification-email delivery is not available right now.",
                    retryable=True,
                ) from exc
            token = payload.get("access_token") if isinstance(payload, dict) else None
            if not isinstance(token, str) or not token:
                raise EmailVerificationError(
                    503,
                    "VERIFICATION_EMAIL_AUTH_FAILED",
                    "Verification-email delivery is not available right now.",
                    retryable=True,
                )
            expires_in = payload.get("expires_in", 3600)
            ttl = int(expires_in) if isinstance(expires_in, (int, float)) else 3600
            self._access_token = token
            self._access_token_expires_at = time.monotonic() + max(30, ttl - 60)
            return token

    def _validate_configuration(self) -> None:
        if not self.settings.enabled:
            raise EmailVerificationError(
                503,
                "VERIFICATION_EMAIL_RESEND_DISABLED",
                "Verification-email resend is not enabled.",
            )
        parsed = urllib.parse.urlparse(self.settings.issuer)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or not self.settings.management_client_id
            or not self.settings.management_client_secret
        ):
            raise EmailVerificationError(
                503,
                "VERIFICATION_EMAIL_NOT_CONFIGURED",
                "Verification-email delivery is not configured.",
            )
