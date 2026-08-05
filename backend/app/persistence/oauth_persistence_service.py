import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.persistence.database import Database
from app.persistence.models import OAuthConnectionRow, OAuthStateRow


class OAuthPersistenceService:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _hash_state(state: str) -> str:
        return hashlib.sha256(state.encode("utf-8")).hexdigest()

    def create_state(self, state: str, user_id: str, provider: str) -> None:
        now = datetime.now(timezone.utc)
        with self.database.session() as session:
            session.execute(delete(OAuthStateRow).where(OAuthStateRow.expires_at < now))
            session.add(OAuthStateRow(
                state_hash=self._hash_state(state), user_id=user_id, provider=provider,
                expires_at=now + timedelta(minutes=10), created_at=now,
            ))

    def consume_state(self, state: str, provider: str) -> str | None:
        now = datetime.now(timezone.utc)
        with self.database.session() as session:
            row = session.get(OAuthStateRow, self._hash_state(state))
            expires_at = row.expires_at if row is not None else None
            if expires_at is not None and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if row is None or row.provider != provider or expires_at is None or expires_at <= now:
                return None
            user_id = row.user_id
            session.delete(row)
            return user_id

    def upsert_connection(self, *, user_id: str, provider: str, access_token: str,
                          refresh_token: str | None, token_type: str, scopes: list[str],
                          external_account_id: str | None, external_account_name: str | None,
                          external_avatar_url: str | None, expires_at: datetime | None) -> None:
        now = datetime.now(timezone.utc)
        with self.database.session() as session:
            row = session.scalar(select(OAuthConnectionRow).where(
                OAuthConnectionRow.user_id == user_id, OAuthConnectionRow.provider == provider
            ))
            if row is None:
                row = OAuthConnectionRow(id=str(uuid.uuid4()), user_id=user_id, provider=provider, created_at=now)
                session.add(row)
            row.access_token_ciphertext = access_token
            if refresh_token is not None:
                row.refresh_token_ciphertext = refresh_token
            row.token_type = token_type
            row.scopes = scopes
            row.external_account_id = external_account_id
            row.external_account_name = external_account_name
            row.external_avatar_url = external_avatar_url
            row.expires_at = expires_at
            row.updated_at = now

    def get_connection(self, user_id: str, provider: str) -> OAuthConnectionRow | None:
        with self.database.session() as session:
            return session.scalar(select(OAuthConnectionRow).where(
                OAuthConnectionRow.user_id == user_id, OAuthConnectionRow.provider == provider
            ))

    def list_connections(self, user_id: str) -> list[OAuthConnectionRow]:
        with self.database.session() as session:
            return list(session.scalars(select(OAuthConnectionRow).where(OAuthConnectionRow.user_id == user_id)))

    def delete_connection(self, user_id: str, provider: str) -> bool:
        with self.database.session() as session:
            row = session.scalar(select(OAuthConnectionRow).where(
                OAuthConnectionRow.user_id == user_id, OAuthConnectionRow.provider == provider
            ))
            if row is None:
                return False
            session.delete(row)
            return True
