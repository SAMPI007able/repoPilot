from datetime import datetime, timezone

from sqlalchemy import select

from app.models.feature_flag_models import FeatureFlagRecord
from app.persistence.database import Database
from app.persistence.models import FeatureFlagRow


FEATURE_FLAG_DEFAULTS: dict[str, tuple[bool, str]] = {
    "preview": (False, "Show and allow creation of realtime preview environments."),
    "code_quality": (False, "Show code-quality insights in a workspace."),
}


class FeatureFlagNotFoundError(LookupError):
    pass


class FeatureFlagPersistenceService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def ensure_defaults(self) -> None:
        with self.database.session() as session:
            existing = set(session.scalars(select(FeatureFlagRow.key)))
            for key, (enabled, description) in FEATURE_FLAG_DEFAULTS.items():
                if key not in existing:
                    session.add(FeatureFlagRow(
                        key=key,
                        enabled=enabled,
                        description=description,
                        updated_at=datetime.now(timezone.utc),
                    ))

    def client_flags(self) -> dict[str, bool]:
        with self.database.session() as session:
            rows = session.scalars(select(FeatureFlagRow).order_by(FeatureFlagRow.key)).all()
            return {row.key: row.enabled for row in rows}

    def list_flags(self) -> list[FeatureFlagRecord]:
        with self.database.session() as session:
            rows = session.scalars(select(FeatureFlagRow).order_by(FeatureFlagRow.key)).all()
            return [self._to_record(row) for row in rows]

    def is_enabled(self, key: str) -> bool:
        with self.database.session() as session:
            row = session.get(FeatureFlagRow, key)
            return row.enabled if row is not None else False

    def update(self, key: str, enabled: bool, updated_by_user_id: str) -> FeatureFlagRecord:
        with self.database.session() as session:
            row = session.get(FeatureFlagRow, key)
            if row is None:
                raise FeatureFlagNotFoundError(key)
            row.enabled = enabled
            row.updated_at = datetime.now(timezone.utc)
            row.updated_by_user_id = updated_by_user_id
            session.flush()
            return self._to_record(row)

    @staticmethod
    def _to_record(row: FeatureFlagRow) -> FeatureFlagRecord:
        return FeatureFlagRecord(
            key=row.key,
            enabled=row.enabled,
            description=row.description,
            updatedAt=row.updated_at,
            updatedByUserId=row.updated_by_user_id,
        )
