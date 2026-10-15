import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.support_models import (
    AdminSupportTicket,
    SupportCategory,
    SupportTicket,
    SupportTicketStatus,
)
from app.persistence.database import Database
from app.persistence.models import SupportAttachmentRow, SupportTicketRow, UserRow


class SupportTicketNotFoundError(LookupError):
    pass


class SupportTicketTransitionError(RuntimeError):
    pass


class SupportAttachmentNotFoundError(LookupError):
    pass


ALLOWED_STATUS_TRANSITIONS: dict[SupportTicketStatus, set[SupportTicketStatus]] = {
    SupportTicketStatus.OPEN: {SupportTicketStatus.IN_PROGRESS, SupportTicketStatus.COMPLETED},
    SupportTicketStatus.IN_PROGRESS: {SupportTicketStatus.COMPLETED},
    SupportTicketStatus.COMPLETED: set(),
}


class SupportPersistenceService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(
        self, user_id: str, category: SupportCategory, subject: str, description_html: str,
    ) -> AdminSupportTicket:
        now = datetime.now(timezone.utc)
        with self.database.session() as session:
            row = SupportTicketRow(
                id=str(uuid.uuid4()), user_id=user_id, category=category.value,
                subject=subject, description_html=description_html,
                status=SupportTicketStatus.OPEN.value, created_at=now, updated_at=now,
            )
            session.add(row)
            session.flush()
            user = session.get(UserRow, user_id)
            return self._admin_ticket(row, user)

    def list_for_user(self, user_id: str) -> list[SupportTicket]:
        with self.database.session() as session:
            rows = session.scalars(
                select(SupportTicketRow)
                .where(SupportTicketRow.user_id == user_id)
                .order_by(SupportTicketRow.created_at.desc())
                .limit(200)
            ).all()
            return [self._ticket(row) for row in rows]

    def list_all(self, status: SupportTicketStatus | None = None) -> list[AdminSupportTicket]:
        with self.database.session() as session:
            statement = select(SupportTicketRow, UserRow).join(UserRow, UserRow.id == SupportTicketRow.user_id)
            if status is not None:
                statement = statement.where(SupportTicketRow.status == status.value)
            rows = session.execute(statement.order_by(SupportTicketRow.created_at.desc()).limit(500)).all()
            return [self._admin_ticket(row, user) for row, user in rows]

    def update_status(
        self, ticket_id: str, status: SupportTicketStatus, actor_user_id: str,
    ) -> AdminSupportTicket:
        with self.database.session() as session:
            row = session.get(SupportTicketRow, ticket_id)
            if row is None:
                raise SupportTicketNotFoundError(ticket_id)
            current = SupportTicketStatus(row.status)
            if status not in ALLOWED_STATUS_TRANSITIONS[current]:
                raise SupportTicketTransitionError(
                    f"A ticket that is {current.value} cannot be marked {status.value}."
                )
            now = datetime.now(timezone.utc)
            row.status = status.value
            row.status_updated_by_user_id = actor_user_id
            row.updated_at = now
            if status == SupportTicketStatus.IN_PROGRESS:
                row.in_progress_at = now
            elif status == SupportTicketStatus.COMPLETED:
                row.completed_at = now
            session.flush()
            return self._admin_ticket(row, session.get(UserRow, row.user_id))

    def admin_emails(self) -> list[str]:
        with self.database.session() as session:
            return list(session.scalars(
                select(UserRow.primary_email)
                .where(UserRow.role == "ADMIN", UserRow.status == "ACTIVE")
                .order_by(UserRow.primary_email)
            ).all())

    def create_attachment(
        self, user_id: str, storage_key: str, content_type: str, size_bytes: int, attachment_id: str,
    ) -> None:
        with self.database.session() as session:
            session.add(SupportAttachmentRow(
                id=attachment_id, user_id=user_id, storage_key=storage_key,
                content_type=content_type, size_bytes=size_bytes,
                created_at=datetime.now(timezone.utc),
            ))

    def attachment(self, attachment_id: str) -> tuple[str, str]:
        with self.database.session() as session:
            row = session.get(SupportAttachmentRow, attachment_id)
            if row is None:
                raise SupportAttachmentNotFoundError(attachment_id)
            return row.storage_key, row.content_type

    @staticmethod
    def _ticket(row: SupportTicketRow) -> SupportTicket:
        return SupportTicket(
            id=row.id, category=row.category, subject=row.subject,
            descriptionHtml=row.description_html, status=row.status,
            createdAt=row.created_at, updatedAt=row.updated_at,
            inProgressAt=row.in_progress_at, completedAt=row.completed_at,
        )

    @staticmethod
    def _admin_ticket(row: SupportTicketRow, user: UserRow | None) -> AdminSupportTicket:
        return AdminSupportTicket(
            **SupportPersistenceService._ticket(row).model_dump(by_alias=True),
            userId=row.user_id,
            userEmail=user.primary_email if user else "",
            userDisplayName=user.display_name if user else None,
        )
