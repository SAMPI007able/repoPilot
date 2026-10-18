import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, func, select

from app.models.chat_models import ChatMessage, ChatSession, ChatSessionSummary
from app.persistence.database import Database
from app.persistence.models import ChatMessageRow, ChatSessionRow


class ChatSessionNotFoundError(LookupError):
    pass


class ChatPersistenceService:
    MAX_CONTEXT_MESSAGES = int(
        os.getenv(
            "AI_CHAT_MAX_HISTORY_MESSAGES",
            os.getenv("GEMINI_CHAT_MAX_HISTORY_MESSAGES", "6"),
        )
    )
    MAX_CONTEXT_CHARACTERS = int(
        os.getenv(
            "AI_CHAT_MAX_HISTORY_CHARACTERS",
            os.getenv("GEMINI_CHAT_MAX_HISTORY_CHARACTERS", "8000"),
        )
    )
    MAX_MESSAGE_CHARACTERS = int(
        os.getenv(
            "AI_CHAT_MAX_MESSAGE_CHARACTERS",
            os.getenv("GEMINI_CHAT_MAX_MESSAGE_CHARACTERS", "3000"),
        )
    )

    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, user_id: str, workspace_id: str) -> ChatSession:
        now = datetime.now(timezone.utc)
        with self.database.session() as session:
            row = ChatSessionRow(
                id=str(uuid.uuid4()), user_id=user_id, workspace_id=workspace_id,
                created_at=now, updated_at=now,
            )
            session.add(row)
            session.flush()
            return self._to_model(row, [])

    def latest(self, user_id: str, workspace_id: str) -> ChatSession | None:
        with self.database.session() as session:
            row = session.scalar(
                select(ChatSessionRow).where(
                    ChatSessionRow.user_id == user_id,
                    ChatSessionRow.workspace_id == workspace_id,
                    ChatSessionRow.title.is_not(None),
                ).order_by(desc(ChatSessionRow.updated_at)).limit(1)
            )
            if row is None:
                return None
            messages = session.scalars(
                select(ChatMessageRow).where(ChatMessageRow.session_id == row.id)
                .order_by(ChatMessageRow.created_at, ChatMessageRow.id)
            ).all()
            return self._to_model(row, messages)

    def list_sessions(self, user_id: str, workspace_id: str, limit: int = 100) -> list[ChatSessionSummary]:
        with self.database.session() as session:
            rows = session.execute(
                select(ChatSessionRow, func.count(ChatMessageRow.id)).outerjoin(
                    ChatMessageRow, ChatMessageRow.session_id == ChatSessionRow.id,
                ).where(
                    ChatSessionRow.user_id == user_id,
                    ChatSessionRow.workspace_id == workspace_id,
                ).group_by(ChatSessionRow.id).having(func.count(ChatMessageRow.id) > 0).order_by(
                    desc(ChatSessionRow.updated_at)
                ).limit(
                    max(1, min(limit, 200))
                )
            ).all()
            return [ChatSessionSummary(
                id=row.id, workspaceId=row.workspace_id, title=row.title,
                messageCount=message_count, createdAt=row.created_at, updatedAt=row.updated_at,
            ) for row, message_count in rows]

    def get(self, session_id: str, user_id: str, workspace_id: str | None = None) -> ChatSession:
        with self.database.session() as session:
            statement = select(ChatSessionRow).where(
                ChatSessionRow.id == session_id,
                ChatSessionRow.user_id == user_id,
            )
            if workspace_id is not None:
                statement = statement.where(ChatSessionRow.workspace_id == workspace_id)
            row = session.scalar(statement)
            if row is None:
                raise ChatSessionNotFoundError(session_id)
            messages = session.scalars(
                select(ChatMessageRow).where(ChatMessageRow.session_id == row.id)
                .order_by(ChatMessageRow.created_at, ChatMessageRow.id)
            ).all()
            return self._to_model(row, messages)

    def context(self, session_id: str, user_id: str, workspace_id: str) -> list[tuple[str, str]]:
        chat = self.get(session_id, user_id, workspace_id)
        selected: list[tuple[str, str]] = []
        character_count = 0
        for message in reversed(chat.messages[-self.MAX_CONTEXT_MESSAGES:]):
            remaining = self.MAX_CONTEXT_CHARACTERS - character_count
            if remaining <= 0:
                break
            content = message.content[:min(remaining, self.MAX_MESSAGE_CHARACTERS)]
            selected.append((message.role, content))
            character_count += len(content)
        return list(reversed(selected))

    def append_exchange(self, session_id: str, user_id: str, workspace_id: str, question: str, answer: str) -> ChatSession:
        now = datetime.now(timezone.utc)
        with self.database.session() as session:
            row = session.scalar(select(ChatSessionRow).where(
                ChatSessionRow.id == session_id,
                ChatSessionRow.user_id == user_id,
                ChatSessionRow.workspace_id == workspace_id,
            ))
            if row is None:
                raise ChatSessionNotFoundError(session_id)
            if not row.title:
                row.title = question.strip()[:120]
            row.updated_at = now
            session.add_all([
                ChatMessageRow(id=str(uuid.uuid4()), session_id=row.id, role="user", content=question, created_at=now),
                ChatMessageRow(id=str(uuid.uuid4()), session_id=row.id, role="assistant", content=answer, created_at=now + timedelta(microseconds=1)),
            ])
            session.flush()
            messages = session.scalars(
                select(ChatMessageRow).where(ChatMessageRow.session_id == row.id)
                .order_by(ChatMessageRow.created_at, ChatMessageRow.id)
            ).all()
            return self._to_model(row, messages)

    @staticmethod
    def _to_model(row: ChatSessionRow, messages) -> ChatSession:
        return ChatSession(
            id=row.id, workspaceId=row.workspace_id, title=row.title,
            messages=[ChatMessage(id=item.id, role=item.role, content=item.content, createdAt=item.created_at) for item in messages],
            createdAt=row.created_at, updatedAt=row.updated_at,
        )
