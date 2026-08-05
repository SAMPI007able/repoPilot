import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select

from app.models.preview_models import (
    ACTIVE_PREVIEW_STATUSES,
    PreviewEnvironment,
    PreviewEvent,
    PreviewStatus,
)
from app.models.runtime_manifest_models import RuntimeManifest
from app.persistence.database import Database
from app.persistence.models import (
    PreviewEnvironmentRow,
    PreviewEventRow,
    RuntimeManifestRow,
    WorkspaceRow,
)


class PreviewNotFoundError(LookupError):
    pass


class PreviewConflictError(RuntimeError):
    pass


class PreviewManifestNotApprovedError(RuntimeError):
    pass


class PreviewPersistenceService:
    TRANSITIONS = {
        PreviewStatus.QUEUED: {PreviewStatus.CLONING, PreviewStatus.STOPPING, PreviewStatus.FAILED},
        PreviewStatus.CLONING: {PreviewStatus.INSTALLING, PreviewStatus.STOPPING, PreviewStatus.FAILED},
        PreviewStatus.INSTALLING: {PreviewStatus.BUILDING, PreviewStatus.STOPPING, PreviewStatus.FAILED},
        PreviewStatus.BUILDING: {PreviewStatus.STARTING, PreviewStatus.STOPPING, PreviewStatus.FAILED},
        PreviewStatus.STARTING: {PreviewStatus.HEALTH_CHECKING, PreviewStatus.STOPPING, PreviewStatus.FAILED},
        PreviewStatus.HEALTH_CHECKING: {PreviewStatus.READY, PreviewStatus.STOPPING, PreviewStatus.FAILED},
        PreviewStatus.READY: {PreviewStatus.STOPPING, PreviewStatus.FAILED},
        PreviewStatus.STOPPING: {PreviewStatus.STOPPED, PreviewStatus.EXPIRED, PreviewStatus.FAILED},
        PreviewStatus.STOPPED: set(),
        PreviewStatus.EXPIRED: set(),
        PreviewStatus.FAILED: set(),
    }

    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, workspace_id: str, idempotency_key: str, environment_names: list[str]) -> tuple[PreviewEnvironment, bool]:
        now = datetime.now(timezone.utc)
        with self.database.session() as session:
            existing = session.scalar(
                select(PreviewEnvironmentRow).where(
                    PreviewEnvironmentRow.workspace_id == workspace_id,
                    PreviewEnvironmentRow.idempotency_key == idempotency_key,
                )
            )
            if existing:
                return self._to_model(existing), False

            workspace = session.get(WorkspaceRow, workspace_id)
            manifest = session.scalar(
                select(RuntimeManifestRow).where(RuntimeManifestRow.workspace_id == workspace_id)
            )
            if workspace is None or workspace.status != "ready" or not workspace.commit_sha:
                raise PreviewConflictError("The workspace is not ready at an immutable commit.")
            if manifest is None or not manifest.approved or not manifest.supported:
                raise PreviewManifestNotApprovedError("Approve a supported runtime manifest before starting a preview.")

            runtime_manifest = RuntimeManifest.model_validate(manifest.manifest)
            maximum_expires_at = now + timedelta(minutes=runtime_manifest.lifecycle.maximum_lifetime_minutes)
            expires_at = min(
                now + timedelta(minutes=runtime_manifest.lifecycle.idle_timeout_minutes),
                maximum_expires_at,
            )
            preview_id = str(uuid.uuid4())
            row = PreviewEnvironmentRow(
                id=preview_id,
                workspace_id=workspace_id,
                status=PreviewStatus.QUEUED.value,
                repository_url=workspace.repo_url,
                commit_sha=workspace.commit_sha,
                manifest_revision=manifest.revision,
                manifest=manifest.manifest,
                environment_names=environment_names,
                idempotency_key=idempotency_key,
                log_storage_key=f"preview-logs/{preview_id}/console.log",
                expires_at=expires_at,
                maximum_expires_at=maximum_expires_at,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            self._add_event(session, row.id, PreviewStatus.QUEUED, "Preview request queued.", now)
            return self._to_model(row), True

    def get(self, preview_id: str) -> PreviewEnvironment:
        with self.database.session() as session:
            row = session.get(PreviewEnvironmentRow, preview_id)
            if row is None:
                raise PreviewNotFoundError(preview_id)
            return self._to_model(row)

    def latest_for_workspace(self, workspace_id: str) -> PreviewEnvironment:
        with self.database.session() as session:
            row = session.scalar(
                select(PreviewEnvironmentRow)
                .where(PreviewEnvironmentRow.workspace_id == workspace_id)
                .order_by(desc(PreviewEnvironmentRow.created_at))
                .limit(1)
            )
            if row is None:
                raise PreviewNotFoundError(workspace_id)
            return self._to_model(row)

    def active_for_workspace(self, workspace_id: str) -> list[PreviewEnvironment]:
        with self.database.session() as session:
            rows = session.scalars(
                select(PreviewEnvironmentRow).where(
                    PreviewEnvironmentRow.workspace_id == workspace_id,
                    PreviewEnvironmentRow.status.in_([status.value for status in ACTIVE_PREVIEW_STATUSES]),
                )
            ).all()
            return [self._to_model(row) for row in rows]

    def active_ids_for_user(self, owner_user_id: str) -> list[str]:
        with self.database.session() as session:
            return list(session.scalars(
                select(PreviewEnvironmentRow.id)
                .join(WorkspaceRow, WorkspaceRow.id == PreviewEnvironmentRow.workspace_id)
                .where(
                    WorkspaceRow.owner_user_id == owner_user_id,
                    PreviewEnvironmentRow.status.in_([status.value for status in ACTIVE_PREVIEW_STATUSES]),
                )
            ).all())

    def find_by_idempotency(self, workspace_id: str, idempotency_key: str) -> PreviewEnvironment | None:
        with self.database.session() as session:
            row = session.scalar(select(PreviewEnvironmentRow).where(
                PreviewEnvironmentRow.workspace_id == workspace_id,
                PreviewEnvironmentRow.idempotency_key == idempotency_key,
            ))
            return self._to_model(row) if row else None

    def owner_user_id(self, preview_id: str) -> str | None:
        with self.database.session() as session:
            return session.scalar(
                select(WorkspaceRow.owner_user_id)
                .join(PreviewEnvironmentRow, PreviewEnvironmentRow.workspace_id == WorkspaceRow.id)
                .where(PreviewEnvironmentRow.id == preview_id)
            )

    def ids_for_workspace(self, workspace_id: str) -> list[str]:
        with self.database.session() as session:
            return list(session.scalars(
                select(PreviewEnvironmentRow.id).where(
                    PreviewEnvironmentRow.workspace_id == workspace_id
                )
            ).all())

    def events(self, preview_id: str, after: datetime | None = None) -> list[PreviewEvent]:
        with self.database.session() as session:
            if session.get(PreviewEnvironmentRow, preview_id) is None:
                raise PreviewNotFoundError(preview_id)
            statement = select(PreviewEventRow).where(PreviewEventRow.preview_id == preview_id)
            if after:
                statement = statement.where(PreviewEventRow.created_at > after)
            rows = session.scalars(statement.order_by(PreviewEventRow.created_at, PreviewEventRow.id)).all()
            return [self._event_to_model(row) for row in rows]

    def transition(
        self,
        preview_id: str,
        target: PreviewStatus,
        message: str,
        *,
        preview_url: str | None = None,
        internal_url: str | None = None,
        provider_state: dict | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> PreviewEnvironment:
        now = datetime.now(timezone.utc)
        with self.database.session() as session:
            row = session.get(PreviewEnvironmentRow, preview_id, with_for_update=True)
            if row is None:
                raise PreviewNotFoundError(preview_id)
            current = PreviewStatus(row.status)
            if current == target:
                return self._to_model(row)
            if target not in self.TRANSITIONS[current]:
                raise PreviewConflictError(f"Cannot transition preview from {current.value} to {target.value}.")
            row.status = target.value
            row.updated_at = now
            if preview_url is not None:
                row.preview_url = preview_url
            if internal_url is not None:
                row.internal_url = internal_url
            if provider_state is not None:
                row.provider_state = provider_state
            if error_code is not None:
                row.error_code = error_code
            if error_message is not None:
                row.error_message = error_message
            if target == PreviewStatus.READY:
                row.ready_at = now
            if target in {PreviewStatus.STOPPED, PreviewStatus.EXPIRED, PreviewStatus.FAILED}:
                row.stopped_at = now
            self._add_event(session, row.id, target, message, now)
            return self._to_model(row)

    def extend(self, preview_id: str, minutes: int) -> PreviewEnvironment:
        now = datetime.now(timezone.utc)
        with self.database.session() as session:
            row = session.get(PreviewEnvironmentRow, preview_id, with_for_update=True)
            if row is None:
                raise PreviewNotFoundError(preview_id)
            if PreviewStatus(row.status) != PreviewStatus.READY:
                raise PreviewConflictError("Only a ready preview can be extended.")
            current_expiry = self._aware(row.expires_at)
            maximum_expiry = self._aware(row.maximum_expires_at)
            row.expires_at = min(max(current_expiry, now) + timedelta(minutes=minutes), maximum_expiry)
            row.updated_at = now
            self._add_event(session, row.id, PreviewStatus.READY, f"Preview lifetime extended by {minutes} minutes.", now)
            return self._to_model(row)

    def expired_active_ids(self) -> list[str]:
        now = datetime.now(timezone.utc)
        with self.database.session() as session:
            return list(session.scalars(
                select(PreviewEnvironmentRow.id).where(
                    PreviewEnvironmentRow.status.in_([status.value for status in ACTIVE_PREVIEW_STATUSES]),
                    PreviewEnvironmentRow.expires_at <= now,
                )
            ).all())

    def provider_state(self, preview_id: str) -> dict:
        with self.database.session() as session:
            row = session.get(PreviewEnvironmentRow, preview_id)
            if row is None:
                raise PreviewNotFoundError(preview_id)
            return dict(row.provider_state or {})

    def is_owned_by(self, preview_id: str, owner_user_id: str) -> bool:
        with self.database.session() as session:
            return session.scalar(
                select(PreviewEnvironmentRow.id)
                .join(WorkspaceRow, WorkspaceRow.id == PreviewEnvironmentRow.workspace_id)
                .where(
                    PreviewEnvironmentRow.id == preview_id,
                    WorkspaceRow.owner_user_id == owner_user_id,
                )
            ) is not None

    @staticmethod
    def _add_event(session, preview_id: str, status: PreviewStatus, message: str, created_at: datetime) -> None:
        session.add(PreviewEventRow(
            id=str(uuid.uuid4()), preview_id=preview_id, status=status.value,
            message=message, created_at=created_at,
        ))

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _to_model(self, row: PreviewEnvironmentRow) -> PreviewEnvironment:
        return PreviewEnvironment(
            id=row.id, workspaceId=row.workspace_id, status=row.status,
            repositoryUrl=row.repository_url, commitSha=row.commit_sha,
            manifestRevision=row.manifest_revision, manifest=row.manifest,
            previewUrl=row.preview_url, errorCode=row.error_code,
            errorMessage=row.error_message, expiresAt=self._aware(row.expires_at),
            maximumExpiresAt=self._aware(row.maximum_expires_at),
            createdAt=self._aware(row.created_at), updatedAt=self._aware(row.updated_at),
            readyAt=self._aware(row.ready_at) if row.ready_at else None,
            stoppedAt=self._aware(row.stopped_at) if row.stopped_at else None,
            provider=row.provider,
        )

    def _event_to_model(self, row: PreviewEventRow) -> PreviewEvent:
        return PreviewEvent(id=row.id, previewId=row.preview_id, status=row.status, message=row.message, createdAt=self._aware(row.created_at))
