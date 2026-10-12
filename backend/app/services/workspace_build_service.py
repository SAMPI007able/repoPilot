import os
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from app.models.code_models import (
    DocumentationAsset,
    RepositoryMetadata,
    WorkspaceBuildJob,
    WorkspaceBuildStage,
)
from app.services.repository_indexer_service import RepositoryIndexerService
from app.services.repository_services import RepositoryService
from app.persistence.workspace_persistence_service import (
    WorkspaceBuildInProgressError,
    WorkspacePersistenceService,
)


class WorkspaceBuildAlreadyRunningError(RuntimeError):
    pass


class WorkspaceBuildService:
    def __init__(
        self,
        repository_service: RepositoryService,
        repository_indexer: RepositoryIndexerService,
        workspace_dir: str,
        persistence_service: WorkspacePersistenceService,
        max_parallel_jobs: int = 2,
        parse_workers: int = 3,
    ) -> None:
        self.repository_service = repository_service
        self.repository_indexer = repository_indexer
        self.workspace_dir = workspace_dir
        self.persistence_service = persistence_service
        self.parse_workers = max(1, parse_workers)
        self._executor = ThreadPoolExecutor(max_workers=max(1, max_parallel_jobs))
        self._lock = threading.RLock()
        self._jobs: dict[str, WorkspaceBuildJob] = {}
        self._active_by_workspace: dict[str, str] = {}
        os.makedirs(self.workspace_dir, exist_ok=True)

    def start_build(
        self,
        git_url: str,
        documents: list[tuple[str, bytes]] | None = None,
        owner_user_id: str | None = None,
        clone_authorization: str | None = None,
        trusted_provider_url: bool = False,
        branch: str | None = None,
    ) -> WorkspaceBuildJob:
        git_url = git_url.strip() if trusted_provider_url else self.repository_service.validate_public_repository_url(git_url)
        repository_name = self.repository_service.extract_repo_name(git_url)
        if not repository_name:
            raise ValueError("Could not determine a repository name from githubUrl.")

        with self._lock:
            build_key = self._build_key(git_url, branch)
            active_job_id = self._active_by_workspace.get(build_key)
            if active_job_id:
                active_job = self._jobs[active_job_id]
                if active_job.status in {"queued", "running"}:
                    raise WorkspaceBuildAlreadyRunningError(
                        f"Repository '{git_url}' is already being built."
                    )

            workspace = self.persistence_service.create_workspace(git_url, repository_name, owner_user_id)
            job = WorkspaceBuildJob(
                jobId=uuid.uuid4().hex,
                workspaceId=workspace.id,
                stages=self._create_stages(),
            )
            self._jobs[job.jobId] = job
            self._active_by_workspace[build_key] = job.jobId
            self.persistence_service.create_build(job)
            self._executor.submit(
                self._run_build,
                job.jobId,
                git_url,
                repository_name,
                documents or [],
                clone_authorization,
                branch,
            )
            return job.model_copy(deep=True)

    def get_job(self, job_id: str, owner_user_id: str | None = None) -> WorkspaceBuildJob | None:
        return self.persistence_service.get_build(job_id, owner_user_id=owner_user_id)

    def get_completed_metadata(self, workspace_id: str) -> RepositoryMetadata | None:
        return self.persistence_service.load_metadata(workspace_id)

    def list_workspaces(self, owner_user_id: str | None = None):
        return self.persistence_service.list_workspaces(owner_user_id)

    def get_workspace(self, workspace_id: str, owner_user_id: str | None = None):
        return self.persistence_service.get_workspace(workspace_id, owner_user_id)

    def delete_workspace(self, workspace_id: str, owner_user_id: str | None = None) -> bool:
        with self._lock:
            active_job_ids = set(self._active_by_workspace.values())
            if any(
                job_id in active_job_ids and job.workspaceId == workspace_id
                for job_id, job in self._jobs.items()
            ):
                raise WorkspaceBuildInProgressError(
                    "A workspace cannot be removed while its build is in progress."
                )
        return self.persistence_service.delete_workspace(workspace_id, owner_user_id)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True)

    def _run_build(
        self,
        job_id: str,
        git_url: str,
        repository_name: str,
        documents: list[tuple[str, bytes]],
        clone_authorization: str | None,
        branch: str | None,
    ) -> None:
        workspace_id = self._jobs[job_id].workspaceId
        temporary_root: str | None = None
        artifact_persisted = False
        self._set_job_status(job_id, "running")

        try:
            temporary_root = tempfile.mkdtemp(prefix=f"{job_id}-", dir=self.workspace_dir)
            destination_path = os.path.join(temporary_root, "repository")
            self._update_stage(job_id, "clone", "running")
            if clone_authorization or branch:
                self.repository_service.clone_repository(
                    git_url,
                    destination_path,
                    authorization=clone_authorization,
                    branch=branch,
                )
            else:
                self.repository_service.clone_repository(git_url, destination_path)
            uploaded_docs = self._save_project_documents(destination_path, documents)
            commit_sha = self.repository_service.get_commit_sha(destination_path)
            self._update_stage(job_id, "clone", "completed")

            metadata = self.repository_indexer.index_repository_parallel(
                repository_name,
                destination_path,
                uploaded_docs=uploaded_docs,
                progress=lambda stage_id, status, detail=None: self._update_stage(
                    job_id, stage_id, status, detail
                ),
                parse_workers=self.parse_workers,
            )

            with self._lock:
                job = self._jobs[job_id]
                job.metadata = metadata
                job.status = "completed"
                completed_job = job.model_copy(deep=True)
            self.persistence_service.complete_build(
                completed_job,
                metadata,
                commit_sha,
            )
            artifact_persisted = True
        except Exception as exc:
            with self._lock:
                job = self._jobs[job_id]
                job.status = "failed"
                job.error = str(exc)
                for stage in job.stages:
                    if stage.status == "running":
                        stage.status = "failed"
                failed_job = job.model_copy(deep=True)
            self.persistence_service.fail_build(failed_job)
        finally:
            cleanup_error: Exception | None = None
            try:
                if temporary_root is not None:
                    self.repository_service.delete_repository(temporary_root)
            except Exception as exc:
                cleanup_error = exc
            finally:
                with self._lock:
                    build_key = self._build_key(git_url, branch)
                    if self._active_by_workspace.get(build_key) == job_id:
                        self._active_by_workspace.pop(build_key, None)

            if cleanup_error is not None:
                with self._lock:
                    job = self._jobs[job_id]
                    job.status = "failed"
                    cleanup_message = (
                        "The repository index was persisted, but its temporary checkout "
                        if artifact_persisted
                        else "The workspace build failed and its temporary checkout "
                    )
                    cleanup_message += f"could not be removed: {cleanup_error}"
                    job.error = (
                        f"{job.error} {cleanup_message}"
                        if job.error
                        else cleanup_message
                    )
                    failed_job = job.model_copy(deep=True)
                self.persistence_service.fail_build(failed_job)

    @staticmethod
    def _build_key(git_url: str, branch: str | None) -> str:
        return f"{git_url}#{branch or ''}"

    def _set_job_status(self, job_id: str, status: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = status
            job_snapshot = job.model_copy(deep=True)
        self.persistence_service.update_build(job_snapshot)

    def _update_stage(
        self,
        job_id: str,
        stage_id: str,
        status: str,
        detail: str | None = None,
    ) -> None:
        with self._lock:
            stage = next(stage for stage in self._jobs[job_id].stages if stage.id == stage_id)
            stage.status = status
            if detail:
                stage.detail = detail
            job_snapshot = self._jobs[job_id].model_copy(deep=True)
        self.persistence_service.update_build(job_snapshot)

    def _create_stages(self) -> list[WorkspaceBuildStage]:
        stages = [
            WorkspaceBuildStage(id="clone", label="Repository clone", detail="Cloning workspace source"),
            WorkspaceBuildStage(id="scan", label="Source discovery", detail="Scanning supported source files"),
            WorkspaceBuildStage(
                id="documentation",
                label="Documentation",
                detail="Extracting project documentation",
            ),
            WorkspaceBuildStage(
                id="package",
                label="Package intelligence",
                detail="Detecting frameworks and dependencies",
            ),
        ]
        stages.extend(
            WorkspaceBuildStage(
                id=f"parse_{worker_index}",
                label=f"Parser batch {worker_index}",
                detail="Parsing files and symbols in parallel",
            )
            for worker_index in range(1, self.parse_workers + 1)
        )
        stages.extend(
            [
                WorkspaceBuildStage(
                    id="relationships",
                    label="Dependency graph",
                    detail="Resolving source relationships",
                ),
                WorkspaceBuildStage(
                    id="finalize",
                    label="Finalize workspace",
                    detail="Combining repository metadata",
                ),
            ]
        )
        return stages

    def _save_project_documents(
        self,
        workspace_path: str,
        documents: list[tuple[str, bytes]],
    ) -> list[DocumentationAsset]:
        if not documents:
            return []

        documentation_dir = os.path.join(workspace_path, "project_docs")
        os.makedirs(documentation_dir, exist_ok=True)
        assets: list[DocumentationAsset] = []

        for original_filename, contents in documents:
            filename = os.path.basename(original_filename)
            target_path = os.path.join(documentation_dir, filename)
            with open(target_path, "wb") as saved_file:
                saved_file.write(contents)

            extension = os.path.splitext(filename)[1].lower()
            if extension in {".md", ".txt", ".json", ".yaml", ".yml", ".rst", ".xml", ".csv"}:
                source = contents.decode("utf-8", errors="ignore")
            elif extension == ".pdf":
                source = (
                    f"[Uploaded PDF document '{filename}' saved to project_docs. "
                    "Text extraction is not yet supported.]"
                )
            elif extension in {".docx", ".pptx"}:
                source = (
                    f"[Uploaded document '{filename}' saved to project_docs. "
                    "Text extraction is not yet supported.]"
                )
            else:
                source = contents.decode("utf-8", errors="ignore")

            assets.append(
                DocumentationAsset(
                    path=os.path.relpath(target_path, workspace_path).replace("\\", "/"),
                    source=source,
                )
            )

        return assets
