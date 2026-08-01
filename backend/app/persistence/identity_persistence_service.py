import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.identity_models import CurrentUserResponse, Principal, TokenClaims, UserRole, UserStatus
from app.persistence.database import Database
from app.persistence.models import AuthIdentityRow, UserRow
from app.services.authentication import AuthenticationError


class IdentityPersistenceService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def authenticate(self, claims: TokenClaims) -> Principal:
        now = datetime.now(timezone.utc)
        with self.database.session() as session:
            identity = session.scalar(select(AuthIdentityRow).where(
                AuthIdentityRow.issuer == claims.issuer,
                AuthIdentityRow.subject == claims.subject,
            ))
            if identity is None:
                if not claims.email:
                    raise AuthenticationError(403, "AUTH_EMAIL_REQUIRED", "The identity provider did not supply an email address.")
                user = UserRow(
                    id=str(uuid.uuid4()),
                    primary_email=claims.email.strip().lower(),
                    display_name=claims.display_name,
                    avatar_url=claims.avatar_url,
                    status=(UserStatus.ACTIVE.value if claims.email_verified else UserStatus.PENDING_VERIFICATION.value),
                    role=UserRole.USER.value,
                    email_verified=claims.email_verified,
                    created_at=now,
                    updated_at=now,
                    last_login_at=now,
                )
                identity = AuthIdentityRow(
                    id=str(uuid.uuid4()), user_id=user.id, issuer=claims.issuer,
                    subject=claims.subject, provider=claims.provider,
                    created_at=now, last_authenticated_at=now,
                )
                session.add_all([user, identity])
            else:
                user = session.get(UserRow, identity.user_id)
                if user is None:
                    raise AuthenticationError(401, "AUTH_IDENTITY_INVALID", "The identity is no longer available.")
                identity.last_authenticated_at = now
                user.last_login_at = now
                user.updated_at = now
                if claims.email_verified and not user.email_verified:
                    user.email_verified = True
                    if user.status == UserStatus.PENDING_VERIFICATION.value:
                        user.status = UserStatus.ACTIVE.value
                if claims.display_name:
                    user.display_name = claims.display_name
                if claims.avatar_url:
                    user.avatar_url = claims.avatar_url
            session.flush()
            return self._principal(user)

    def current_user(self, user_id: str) -> CurrentUserResponse:
        with self.database.session() as session:
            user = session.get(UserRow, user_id)
            if user is None:
                raise AuthenticationError(401, "AUTH_IDENTITY_INVALID", "The user is no longer available.")
            return CurrentUserResponse(
                id=user.id, primaryEmail=user.primary_email, displayName=user.display_name,
                avatarUrl=user.avatar_url, status=user.status, role=user.role,
                emailVerified=user.email_verified, createdAt=user.created_at,
                lastLoginAt=user.last_login_at,
            )

    @staticmethod
    def _principal(user: UserRow) -> Principal:
        return Principal(
            user_id=user.id, email=user.primary_email, display_name=user.display_name,
            avatar_url=user.avatar_url, status=user.status, role=user.role,
            email_verified=user.email_verified,
        )
