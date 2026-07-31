import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.runtime_manifest_models import (
    RuntimeManifest,
    RuntimeManifestAnalysis,
    RuntimeManifestRecord,
)
from app.persistence.database import Database
from app.persistence.models import RuntimeManifestRow, WorkspaceRow


class RuntimeManifestNotFoundError(LookupError):
    pass


class RuntimeManifestRevisionConflictError(RuntimeError):
    pass


class RuntimeManifestPersistenceService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save_analysis(
        self,
        workspace_id: str,
        analysis: RuntimeManifestAnalysis,
    ) -> RuntimeManifestRecord:
        now = datetime.now(timezone.utc)
        with self.database.session() as session:
            if session.get(WorkspaceRow, workspace_id) is None:
                raise RuntimeManifestNotFoundError(workspace_id)
            row = session.scalar(
                select(RuntimeManifestRow).where(
                    RuntimeManifestRow.workspace_id == workspace_id
                )
            )
            if row is None:
                row = RuntimeManifestRow(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    manifest_version=analysis.manifest.version,
                    manifest={},
                    analysis_summary={},
                    revision=1,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.revision += 1
                row.updated_at = now
            self._apply_analysis(row, analysis)
            row.approved = False
            row.approved_at = None
        return self.get(workspace_id)

    def update_manifest(
        self,
        workspace_id: str,
        manifest: RuntimeManifest,
        expected_revision: int,
        supported: bool,
        unsupported_reasons: list[str],
    ) -> RuntimeManifestRecord:
        with self.database.session() as session:
            row = self._get_row(session, workspace_id)
            self._check_revision(row, expected_revision)
            row.manifest_version = manifest.version
            row.manifest = manifest.model_dump(mode="json", by_alias=True)
            row.approved = False
            row.approved_at = None
            row.supported = supported
            row.unsupported_reasons = unsupported_reasons
            row.revision += 1
            row.updated_at = datetime.now(timezone.utc)
        return self.get(workspace_id)

    def approve(
        self,
        workspace_id: str,
        expected_revision: int,
    ) -> RuntimeManifestRecord:
        with self.database.session() as session:
            row = self._get_row(session, workspace_id)
            self._check_revision(row, expected_revision)
            row.approved = True
            row.approved_at = datetime.now(timezone.utc)
            row.revision += 1
            row.updated_at = row.approved_at
        return self.get(workspace_id)

    def get(self, workspace_id: str) -> RuntimeManifestRecord:
        with self.database.session() as session:
            row = session.scalar(
                select(RuntimeManifestRow).where(
                    RuntimeManifestRow.workspace_id == workspace_id
                )
            )
            if row is None:
                raise RuntimeManifestNotFoundError(workspace_id)
            return self._to_record(row)

    def _apply_analysis(
        self,
        row: RuntimeManifestRow,
        analysis: RuntimeManifestAnalysis,
    ) -> None:
        row.manifest_version = analysis.manifest.version
        row.manifest = analysis.manifest.model_dump(mode="json", by_alias=True)
        row.analysis_summary = analysis.summary.model_dump(mode="json", by_alias=True)
        row.evidence = [item.model_dump(mode="json", by_alias=True) for item in analysis.evidence]
        row.warnings = analysis.warnings
        row.unsupported_reasons = analysis.unsupported_reasons
        row.supported = analysis.supported

    def _get_row(self, session, workspace_id: str) -> RuntimeManifestRow:
        row = session.scalar(
            select(RuntimeManifestRow).where(
                RuntimeManifestRow.workspace_id == workspace_id
            )
        )
        if row is None:
            raise RuntimeManifestNotFoundError(workspace_id)
        return row

    def _check_revision(
        self,
        row: RuntimeManifestRow,
        expected_revision: int,
    ) -> None:
        if row.revision != expected_revision:
            raise RuntimeManifestRevisionConflictError(
                f"Runtime manifest revision {expected_revision} is stale; current revision is {row.revision}."
            )

    def _to_record(self, row: RuntimeManifestRow) -> RuntimeManifestRecord:
        return RuntimeManifestRecord(
            workspaceId=row.workspace_id,
            manifest=RuntimeManifest.model_validate(row.manifest),
            summary=row.analysis_summary,
            evidence=row.evidence,
            warnings=row.warnings,
            supported=row.supported,
            unsupportedReasons=row.unsupported_reasons,
            approved=row.approved,
            revision=row.revision,
            createdAt=row.created_at,
            updatedAt=row.updated_at,
            approvedAt=row.approved_at,
        )
