from fastapi import Header

from app.models.identity_models import Principal, UserStatus
from app.persistence.identity_persistence_service import IdentityPersistenceService
from app.services.authentication import AuthenticationError, TokenVerifier


class AuthenticationDependencies:
    def __init__(self, identities: IdentityPersistenceService, verifier: TokenVerifier) -> None:
        self.identities = identities
        self.verifier = verifier

    def principal(self, authorization: str | None = Header(default=None)) -> Principal:
        if not authorization or not authorization.startswith("Bearer "):
            raise AuthenticationError(401, "AUTH_REQUIRED", "Authentication is required.")
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            raise AuthenticationError(401, "AUTH_REQUIRED", "Authentication is required.")
        return self.identities.authenticate(self.verifier.verify(token))

    def active_principal(self, authorization: str | None = Header(default=None)) -> Principal:
        principal = self.principal(authorization)
        if principal.status == UserStatus.PENDING_VERIFICATION:
            raise AuthenticationError(403, "EMAIL_VERIFICATION_REQUIRED", "Verify your email before using TestForge resources.")
        if principal.status != UserStatus.ACTIVE:
            raise AuthenticationError(403, "USER_NOT_ACTIVE", "This TestForge account is not active.")
        return principal
