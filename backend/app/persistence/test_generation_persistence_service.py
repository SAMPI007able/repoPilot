import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, select

from app.models.generation_models import TestGenerationRecord, TestGenerationSummary
from app.persistence.database import Database
from app.persistence.models import TestGenerationRow


class TestGenerationPersistenceService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_generations(self, user_id: str, workspace_id: str, limit: int = 100) -> list[TestGenerationSummary]:
        with self.database.session() as session:
            rows = session.scalars(
                select(TestGenerationRow).where(
                    TestGenerationRow.user_id == user_id,
                    TestGenerationRow.workspace_id == workspace_id,
                ).order_by(desc(TestGenerationRow.created_at)).limit(max(1, min(limit, 200)))
            ).all()
            return [self._to_summary(row) for row in rows]

    def get_generation(
        self, generation_id: str, user_id: str, workspace_id: str,
    ) -> TestGenerationRecord | None:
        with self.database.session() as session:
            row = session.scalar(select(TestGenerationRow).where(
                TestGenerationRow.id == generation_id,
                TestGenerationRow.user_id == user_id,
                TestGenerationRow.workspace_id == workspace_id,
            ))
            return self._to_model(row) if row is not None else None

    def find_cached(self, user_id: str, workspace_id: str, request_hash: str) -> TestGenerationRow | None:
        with self.database.session() as session:
            return session.scalar(
                select(TestGenerationRow).where(
                    TestGenerationRow.user_id == user_id,
                    TestGenerationRow.workspace_id == workspace_id,
                    TestGenerationRow.request_hash == request_hash,
                ).order_by(desc(TestGenerationRow.created_at)).limit(1)
            )

    def create(
        self, *, user_id: str, workspace_id: str, mode: str, test_type: str,
        target: str | None, scenario: str | None, prompt: str, markdown: str,
        request_hash: str, cache_hit: bool = False,
    ) -> TestGenerationRecord:
        with self.database.session() as session:
            row = TestGenerationRow(
                id=str(uuid.uuid4()), user_id=user_id, workspace_id=workspace_id,
                mode=mode, test_type=test_type, target=target, scenario=scenario,
                prompt=prompt, markdown=markdown, request_hash=request_hash,
                cache_hit=cache_hit, created_at=datetime.now(timezone.utc),
            )
            session.add(row)
            session.flush()
            return self._to_model(row)

    @staticmethod
    def _to_model(row: TestGenerationRow) -> TestGenerationRecord:
        return TestGenerationRecord(
            id=row.id, workspaceId=row.workspace_id, mode=row.mode,
            testType=row.test_type, target=row.target, scenario=row.scenario,
            markdown=row.markdown, cacheHit=row.cache_hit, createdAt=row.created_at,
        )

    @staticmethod
    def _to_summary(row: TestGenerationRow) -> TestGenerationSummary:
        return TestGenerationSummary(
            id=row.id, workspaceId=row.workspace_id, mode=row.mode,
            testType=row.test_type, target=row.target, scenario=row.scenario,
            cacheHit=row.cache_hit, createdAt=row.created_at,
        )
