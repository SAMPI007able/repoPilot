import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select

from app.models.admin_models import (
    AdminBrowserSession,
    AdminDashboard,
    AdminLog,
    AdminPreview,
    AdminUsage,
    AdminUser,
)
from app.models.preview_models import ACTIVE_PREVIEW_STATUSES
from app.persistence.database import Database
from app.persistence.models import (
    AdminLogRow,
    ArtifactRow,
    BrowserSessionRow,
    PreviewEnvironmentRow,
    UsageEventRow,
    UserRow,
    WorkspaceBuildRow,
    WorkspaceRow,
)


class AdminResourceNotFoundError(LookupError):
    pass


class AdminConflictError(RuntimeError):
    pass


class AdminService:
    ACTIVE_BROWSER_STATUSES = ("queued", "starting", "active")

    def __init__(self, database: Database) -> None:
        self.database = database

    def dashboard(self) -> AdminDashboard:
        with self.database.session() as session:
            return AdminDashboard(
                totalUsers=session.scalar(select(func.count(UserRow.id))) or 0,
                activePreviews=session.scalar(select(func.count(PreviewEnvironmentRow.id)).where(
                    PreviewEnvironmentRow.status.in_([status.value for status in ACTIVE_PREVIEW_STATUSES])
                )) or 0,
                activeBrowserSessions=session.scalar(select(func.count(BrowserSessionRow.id)).where(
                    BrowserSessionRow.status.in_(self.ACTIVE_BROWSER_STATUSES)
                )) or 0,
            )

    def users(self, query: str = "") -> list[AdminUser]:
        with self.database.session() as session:
            statement = select(UserRow)
            if query.strip():
                pattern = f"%{query.strip()}%"
                statement = statement.where(or_(
                    UserRow.primary_email.ilike(pattern), UserRow.display_name.ilike(pattern)
                ))
            rows = session.scalars(statement.order_by(UserRow.created_at.desc()).limit(200)).all()
            return [AdminUser(
                id=row.id, primaryEmail=row.primary_email, displayName=row.display_name,
                status=row.status, role=row.role, createdAt=row.created_at, lastLoginAt=row.last_login_at,
            ) for row in rows]

    def set_suspended(self, user_id: str, suspended: bool, actor_user_id: str) -> AdminUser:
        if user_id == actor_user_id and suspended:
            raise AdminConflictError("You cannot suspend your own administrator account.")
        with self.database.session() as session:
            row = session.get(UserRow, user_id)
            if row is None:
                raise AdminResourceNotFoundError(user_id)
            row.status = "SUSPENDED" if suspended else "ACTIVE"
            row.updated_at = datetime.now(timezone.utc)
            session.flush()
            return AdminUser(
                id=row.id, primaryEmail=row.primary_email, displayName=row.display_name,
                status=row.status, role=row.role, createdAt=row.created_at, lastLoginAt=row.last_login_at,
            )

    def delete_user(self, user_id: str, actor_user_id: str) -> None:
        if user_id == actor_user_id:
            raise AdminConflictError("You cannot delete your own administrator account.")
        with self.database.session() as session:
            row = session.get(UserRow, user_id)
            if row is None:
                raise AdminResourceNotFoundError(user_id)
            session.delete(row)

    def active_previews(self) -> list[AdminPreview]:
        with self.database.session() as session:
            rows = session.execute(
                select(PreviewEnvironmentRow, WorkspaceRow.owner_user_id, UserRow.primary_email)
                .join(WorkspaceRow, WorkspaceRow.id == PreviewEnvironmentRow.workspace_id)
                .outerjoin(UserRow, UserRow.id == WorkspaceRow.owner_user_id)
                .where(PreviewEnvironmentRow.status.in_([status.value for status in ACTIVE_PREVIEW_STATUSES]))
                .order_by(PreviewEnvironmentRow.created_at.desc())
            ).all()
            return [AdminPreview(
                id=preview.id, workspaceId=preview.workspace_id, userId=user_id,
                userEmail=email, repositoryUrl=preview.repository_url, status=preview.status,
                provider=preview.provider, createdAt=preview.created_at, expiresAt=preview.expires_at,
            ) for preview, user_id, email in rows]

    def active_browser_sessions(self) -> list[AdminBrowserSession]:
        with self.database.session() as session:
            rows = session.execute(
                select(BrowserSessionRow, UserRow.primary_email)
                .outerjoin(UserRow, UserRow.id == BrowserSessionRow.user_id)
                .where(BrowserSessionRow.status.in_(self.ACTIVE_BROWSER_STATUSES))
                .order_by(BrowserSessionRow.created_at.desc())
            ).all()
            return [AdminBrowserSession(
                id=row.id, userId=row.user_id, userEmail=email, status=row.status,
                provider=row.provider, createdAt=row.created_at, expiresAt=row.expires_at,
            ) for row, email in rows]

    def terminate_browser_session(self, session_id: str) -> None:
        with self.database.session() as session:
            row = session.get(BrowserSessionRow, session_id)
            if row is None:
                raise AdminResourceNotFoundError(session_id)
            row.status = "terminated"
            row.terminated_at = datetime.now(timezone.utc)
            row.updated_at = row.terminated_at

    def record_usage(self, user_id: str, category: str, quantity: int = 1) -> None:
        with self.database.session() as session:
            session.add(UsageEventRow(
                id=str(uuid.uuid4()), user_id=user_id, category=category,
                quantity=quantity, created_at=datetime.now(timezone.utc),
            ))

    def usage(self) -> list[AdminUsage]:
        with self.database.session() as session:
            users = session.scalars(select(UserRow).order_by(UserRow.primary_email)).all()
            result: list[AdminUsage] = []
            for user in users:
                ai_requests = session.scalar(select(func.coalesce(func.sum(UsageEventRow.quantity), 0)).where(
                    UsageEventRow.user_id == user.id, UsageEventRow.category == "ai_request"
                )) or 0
                preview_rows = session.execute(
                    select(PreviewEnvironmentRow.created_at, PreviewEnvironmentRow.stopped_at, PreviewEnvironmentRow.updated_at)
                    .join(WorkspaceRow, WorkspaceRow.id == PreviewEnvironmentRow.workspace_id)
                    .where(WorkspaceRow.owner_user_id == user.id)
                ).all()
                preview_minutes = sum(max(0, int(((stopped or updated) - created).total_seconds() // 60))
                                      for created, stopped, updated in preview_rows)
                storage_bytes = session.scalar(
                    select(func.coalesce(func.sum(ArtifactRow.compressed_size), 0))
                    .join(WorkspaceRow, WorkspaceRow.id == ArtifactRow.workspace_id)
                    .where(WorkspaceRow.owner_user_id == user.id)
                ) or 0
                result.append(AdminUsage(
                    userId=user.id, primaryEmail=user.primary_email, aiRequests=int(ai_requests),
                    previewCount=len(preview_rows), previewMinutes=preview_minutes,
                    storageBytes=int(storage_bytes),
                ))
            return result

    def record_log(self, category: str, message: str, *, code: str | None = None, user_id: str | None = None) -> None:
        with self.database.session() as session:
            session.add(AdminLogRow(
                id=str(uuid.uuid4()), category=category, severity="error", code=code,
                message=message[:2000], user_id=user_id, created_at=datetime.now(timezone.utc),
            ))

    def logs(self) -> list[AdminLog]:
        with self.database.session() as session:
            logs = [AdminLog(
                id=row.id, category=row.category, severity=row.severity, code=row.code,
                message=row.message, userId=row.user_id, createdAt=row.created_at,
            ) for row in session.scalars(select(AdminLogRow).order_by(AdminLogRow.created_at.desc()).limit(200)).all()]
            failed_builds = session.scalars(
                select(WorkspaceBuildRow).where(WorkspaceBuildRow.status == "failed")
                .order_by(WorkspaceBuildRow.created_at.desc()).limit(100)
            ).all()
            logs.extend(AdminLog(
                id=f"build-{row.id}", category="preview_build", severity="error",
                code="WORKSPACE_BUILD_FAILED", message=row.error or "Workspace build failed.",
                userId=None, createdAt=row.completed_at or row.created_at,
            ) for row in failed_builds)
            failed_previews = session.execute(
                select(PreviewEnvironmentRow, WorkspaceRow.owner_user_id)
                .join(WorkspaceRow, WorkspaceRow.id == PreviewEnvironmentRow.workspace_id)
                .where(PreviewEnvironmentRow.status == "failed")
                .order_by(PreviewEnvironmentRow.updated_at.desc()).limit(100)
            ).all()
            logs.extend(AdminLog(
                id=f"preview-{row.id}", category="runtime", severity="error",
                code=row.error_code, message=row.error_message or "Preview runtime failed.",
                userId=user_id, createdAt=row.updated_at,
            ) for row, user_id in failed_previews)
            return sorted(logs, key=lambda item: item.created_at, reverse=True)[:200]
