import json
import os
from typing import Protocol
import urllib.error
import urllib.request

import jwt
from jwt import PyJWKClient

from app.models.identity_models import TokenClaims


class AuthenticationError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable


class TokenVerifier(Protocol):
    def verify(self, token: str) -> TokenClaims: ...


class OIDCTokenVerifier:
    def __init__(self, issuer: str, audience: str, jwks_url: str) -> None:
        self.issuer = issuer.rstrip("/") + "/"
        self.audience = audience
        self.jwks_client = PyJWKClient(jwks_url)

    def verify(self, token: str) -> TokenClaims:
        if token.count(".") == 4:
            raise AuthenticationError(
                401,
                "AUTH_TOKEN_AUDIENCE_REQUIRED",
                "Auth0 issued an opaque UserInfo token. Configure VITE_OIDC_AUDIENCE to match OIDC_AUDIENCE, then sign in again.",
            )
        if token.count(".") != 2:
            raise AuthenticationError(401, "AUTH_TOKEN_INVALID", "The access token format is invalid.")
        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iat", "iss", "sub"]},
            )
            self._validate_payload(payload)
        except AuthenticationError:
            raise
        except Exception as exc:
            raise AuthenticationError(401, "AUTH_TOKEN_INVALID", "The access token is invalid or expired.") from exc

        try:
            profile = self._userinfo(token)
            if profile.get("sub") != payload.get("sub"):
                raise AuthenticationError(401, "AUTH_CLAIMS_INVALID", "The UserInfo subject does not match the access token.")
            payload = {**profile, **payload}
        except AuthenticationError:
            raise
        except Exception:
            pass
        return _claims(payload, provider="oidc")

    def _validate_payload(self, payload: dict) -> None:
        issuer = payload.get("iss")
        subject = payload.get("sub")
        if not isinstance(issuer, str) or not isinstance(subject, str):
            raise AuthenticationError(401, "AUTH_CLAIMS_INVALID", "The access token identity claims are invalid.")
        if issuer != self.issuer:
            raise AuthenticationError(401, "AUTH_TOKEN_INVALID", "The access token issuer is invalid.")
        if not self._audience_matches(payload):
            raise AuthenticationError(401, "AUTH_TOKEN_INVALID", "The access token audience is invalid.")

    def _audience_matches(self, payload: dict) -> bool:
        aud = payload.get("aud")
        if isinstance(aud, str):
            return aud == self.audience
        if isinstance(aud, list):
            return any(item == self.audience for item in aud)
        return False

    def _userinfo(self, token: str) -> dict:
        url = f"{self.issuer}userinfo"
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise AuthenticationError(401, "AUTH_CLAIMS_INVALID", "The userinfo response was invalid.")
        return payload


class DevelopmentTokenVerifier:
    def __init__(self, expected_token: str, email: str) -> None:
        self.expected_token = expected_token
        self.email = email

    def verify(self, token: str) -> TokenClaims:
        import secrets

        if not secrets.compare_digest(token, self.expected_token):
            raise AuthenticationError(401, "AUTH_TOKEN_INVALID", "The development access token is invalid.")
        return TokenClaims(
            issuer="https://development.testforge.local",
            subject=self.email,
            email=self.email,
            email_verified=True,
            display_name="Local Developer",
            provider="development",
        )


class MisconfiguredTokenVerifier:
    def verify(self, token: str) -> TokenClaims:
        del token
        raise AuthenticationError(503, "AUTH_NOT_CONFIGURED", "OIDC authentication is not configured.")


def create_token_verifier() -> TokenVerifier:
    mode = os.getenv("AUTH_MODE", "oidc").lower()
    if mode == "development":
        if os.getenv("AUTH_ALLOW_INSECURE_DEVELOPMENT", "false").lower() != "true":
            return MisconfiguredTokenVerifier()
        token = os.getenv("AUTH_DEVELOPMENT_TOKEN")
        email = os.getenv("AUTH_DEVELOPMENT_USER_EMAIL", "developer@testforge.local")
        return DevelopmentTokenVerifier(token, email) if token else MisconfiguredTokenVerifier()
    issuer = os.getenv("OIDC_ISSUER")
    audience = os.getenv("OIDC_AUDIENCE")
    jwks_url = os.getenv("OIDC_JWKS_URL")
    if not issuer or not audience or not jwks_url:
        return MisconfiguredTokenVerifier()
    return OIDCTokenVerifier(issuer, audience, jwks_url)


def _claims(payload: dict, provider: str) -> TokenClaims:
    issuer = payload.get("iss")
    subject = payload.get("sub")
    if not isinstance(issuer, str) or not isinstance(subject, str):
        raise AuthenticationError(401, "AUTH_CLAIMS_INVALID", "The access token identity claims are invalid.")
    return TokenClaims(
        issuer=issuer,
        subject=subject,
        email=payload.get("email") if isinstance(payload.get("email"), str) else None,
        email_verified=payload.get("email_verified") is True,
        display_name=payload.get("name") if isinstance(payload.get("name"), str) else None,
        avatar_url=payload.get("picture") if isinstance(payload.get("picture"), str) else None,
        provider=provider,
    )
