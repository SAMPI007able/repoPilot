import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, select

from app.models.code_models import (
    RepositoryMetadata,
    RepositoryStatistics,
    WorkspaceBuildJob,
    WorkspaceBuildStage,
    WorkspaceDetail,
    WorkspaceSummary,
)
from app.persistence.artifact_codec import (
    ARTIFACT_SCHEMA_VERSION,
    RepositoryArtifactCodec,
)
from app.persistence.artifact_store import ArtifactStore
from app.persistence.database import Database
from app.persistence.models import ArtifactRow, WorkspaceBuildRow, WorkspaceRow


class WorkspaceNotFoundError(LookupError):
    pass


class WorkspaceBuildInProgressError(RuntimeError):
    pass


class WorkspacePersistenceService:
    def __init__(
        self,
        database: Database,
        artifact_store: ArtifactStore,
        artifact_codec: RepositoryArtifactCodec | None = None,
    ) -> None:
        self.database = database
        self.artifact_store = artifact_store
        self.artifact_codec = artifact_codec or RepositoryArtifactCodec()

    def create_workspace(self, repo_url: str, repo_name: str) -> WorkspaceSummary:
        workspace = WorkspaceRow(
            id=str(uuid.uuid4()),
            repo_url=repo_url,
            repo_name=repo_name,
            status="queued",
        )
        with self.database.session() as session:
            session.add(workspace)
        return self._to_summary(workspace)

    def create_build(self, job: WorkspaceBuildJob) -> None:
        build = WorkspaceBuildRow(
            id=job.jobId,
            workspace_id=job.workspaceId,
            status=job.status,
            stages=[stage.model_dump(mode="json") for stage in job.stages],
        )
        with self.database.session() as session:
            session.add(build)

    def update_build(self, job: WorkspaceBuildJob) -> None:
        now = datetime.now(timezone.utc)
        with self.database.session() as session:
            build = session.get(WorkspaceBuildRow, job.jobId)
            workspace = session.get(WorkspaceRow, job.workspaceId)
            if build is None or workspace is None:
                raise WorkspaceNotFoundError(job.workspaceId)

            build.status = job.status
            build.stages = [stage.model_dump(mode="json") for stage in job.stages]
            build.error = job.error
            if job.status == "running" and build.started_at is None:
                build.started_at = now
            if job.status in {"completed", "failed"}:
                build.completed_at = now

            if job.status in {"queued", "running", "failed"}:
                workspace.status = job.status
                workspace.error = job.error
                workspace.updated_at = now

    def complete_build(
        self,
        job: WorkspaceBuildJob,
        metadata: RepositoryMetadata,
        commit_sha: str | None,
    ) -> None:
        artifact_id = str(uuid.uuid4())
        commit_segment = commit_sha or "working-tree"
        storage_key = (
            f"repository-indexes/{job.workspaceId}/{commit_segment}/"
            f"index-v{ARTIFACT_SCHEMA_VERSION}-{artifact_id}.json.gz"
        )
        encoded = self.artifact_codec.encode(job.workspaceId, commit_sha, metadata)
        self.artifact_store.put(storage_key, encoded.contents, "application/gzip")

        try:
            verified_contents = self.artifact_store.get(storage_key)
            self.artifact_codec.decode(
                verified_contents,
                expected_checksum=encoded.checksum_sha256,
            )

            now = datetime.now(timezone.utc)
            with self.database.session() as session:
                workspace = session.get(WorkspaceRow, job.workspaceId)
                build = session.get(WorkspaceBuildRow, job.jobId)
                if workspace is None or build is None:
                    raise WorkspaceNotFoundError(job.workspaceId)

                artifact = ArtifactRow(
                    id=artifact_id,
                    workspace_id=job.workspaceId,
                    kind="repository_index",
                    storage_key=storage_key,
                    content_type="application/gzip",
                    schema_version=ARTIFACT_SCHEMA_VERSION,
                    checksum_sha256=encoded.checksum_sha256,
                    compressed_size=encoded.compressed_size,
                )
                session.add(artifact)

                workspace.commit_sha = commit_sha
                workspace.status = "ready"
                workspace.stats = metadata.statistics.model_dump(mode="json")
                workspace.package_info = (
                    metadata.packageInfo.model_dump(mode="json")
                    if metadata.packageInfo
                    else None
                )
                workspace.graph_preview = [
                    relationship.model_dump(mode="json")
                    for relationship in metadata.relationships[:200]
                ]
                workspace.docs_summary = [
                    {
                        "path": document.path,
                        "excerpt": " ".join(
                            document.source.strip().replace("\r", "").split("\n")[:3]
                        )[:300],
                    }
                    for document in metadata.documentation
                ]
                workspace.active_artifact_id = artifact_id
                workspace.error = None
                workspace.indexed_at = now
                workspace.updated_at = now

                build.status = "completed"
                build.stages = [
                    stage.model_dump(mode="json")
                    for stage in job.stages
                ]
                build.error = None
                build.completed_at = now
        except Exception:
            self.artifact_store.delete(storage_key)
            raise

    def fail_build(self, job: WorkspaceBuildJob) -> None:
        self.update_build(job)

    def get_build(self, job_id: str, include_metadata: bool = True) -> WorkspaceBuildJob | None:
        with self.database.session() as session:
            build = session.get(WorkspaceBuildRow, job_id)
            if build is None:
                return None
            job = WorkspaceBuildJob(
                jobId=build.id,
                workspaceId=build.workspace_id,
                status=build.status,
                stages=[
                    WorkspaceBuildStage.model_validate(stage)
                    for stage in build.stages
                ],
                error=build.error,
            )

        if include_metadata and job.status == "completed":
            job.metadata = self.load_metadata(job.workspaceId)
        return job

    def load_metadata(self, workspace_id: str) -> RepositoryMetadata | None:
        with self.database.session() as session:
            workspace = session.get(WorkspaceRow, workspace_id)
            if workspace is None or not workspace.active_artifact_id:
                return None
            artifact = session.get(ArtifactRow, workspace.active_artifact_id)
            if artifact is None:
                return None
            storage_key = artifact.storage_key
            checksum = artifact.checksum_sha256

        contents = self.artifact_store.get(storage_key)
        return self.artifact_codec.decode(contents, expected_checksum=checksum)

    def list_workspaces(self) -> list[WorkspaceSummary]:
        with self.database.session() as session:
            workspaces = session.scalars(
                select(WorkspaceRow).order_by(desc(WorkspaceRow.created_at))
            ).all()
            summaries = []
            for workspace in workspaces:
                latest_build = self._latest_build(session, workspace.id)
                summaries.append(
                    self._to_summary(
                        workspace,
                        stages=self._build_stages(latest_build),
                        job_id=latest_build.id if latest_build else None,
                    )
                )
            return summaries

    def get_workspace(self, workspace_id: str) -> WorkspaceDetail | None:
        with self.database.session() as session:
            workspace = session.get(WorkspaceRow, workspace_id)
            if workspace is None:
                return None
            latest_build = self._latest_build(session, workspace.id)
            summary = self._to_summary(
                workspace,
                stages=self._build_stages(latest_build),
                job_id=latest_build.id if latest_build else None,
            )

        metadata = self.load_metadata(workspace_id)
        if metadata is None:
            return None
        return WorkspaceDetail(**summary.model_dump(), metadata=metadata)

    def delete_workspace(self, workspace_id: str) -> bool:
        with self.database.session() as session:
            workspace = session.get(WorkspaceRow, workspace_id)
            if workspace is None:
                return False
            if workspace.status in {"queued", "running"}:
                raise WorkspaceBuildInProgressError(
                    "A workspace cannot be removed while its build is in progress."
                )
            storage_keys = [artifact.storage_key for artifact in workspace.artifacts]

        for storage_key in storage_keys:
            self.artifact_store.delete(storage_key)

        with self.database.session() as session:
            workspace = session.get(WorkspaceRow, workspace_id)
            if workspace is not None:
                session.delete(workspace)
        return True

    def mark_interrupted_builds_failed(self) -> None:
        now = datetime.now(timezone.utc)
        with self.database.session() as session:
            builds = session.scalars(
                select(WorkspaceBuildRow).where(
                    WorkspaceBuildRow.status.in_(["queued", "running"])
                )
            ).all()
            for build in builds:
                build.status = "failed"
                build.error = "Build was interrupted by an application restart."
                build.completed_at = now
                workspace = session.get(WorkspaceRow, build.workspace_id)
                if workspace:
                    workspace.status = "failed"
                    workspace.error = build.error
                    workspace.updated_at = now

    def _latest_build(self, session, workspace_id: str) -> WorkspaceBuildRow | None:
        return session.scalar(
            select(WorkspaceBuildRow)
            .where(WorkspaceBuildRow.workspace_id == workspace_id)
            .order_by(desc(WorkspaceBuildRow.created_at))
            .limit(1)
        )

    def _build_stages(
        self,
        build: WorkspaceBuildRow | None,
    ) -> list[WorkspaceBuildStage]:
        if build is None:
            return []
        return [
            WorkspaceBuildStage.model_validate(stage)
            for stage in build.stages
        ]

    def _to_summary(
        self,
        workspace: WorkspaceRow,
        stages: list[WorkspaceBuildStage] | None = None,
        job_id: str | None = None,
    ) -> WorkspaceSummary:
        return WorkspaceSummary(
            id=workspace.id,
            jobId=job_id,
            repoUrl=workspace.repo_url,
            repoName=workspace.repo_name,
            status=workspace.status,
            statistics=RepositoryStatistics.model_validate(
                workspace.stats or {"files": 0, "typescript": 0, "javascript": 0}
            ),
            stages=stages or [],
            error=workspace.error,
            createdAt=workspace.created_at,
            updatedAt=workspace.updated_at,
        )
