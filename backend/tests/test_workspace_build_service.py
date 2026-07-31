import tempfile
import time
import unittest
import os
import shutil
from unittest.mock import Mock

from app.models.code_models import RepositoryMetadata, RepositoryStatistics
from app.persistence.artifact_store import LocalArtifactStore
from app.persistence.database import Database
from app.persistence.workspace_persistence_service import WorkspacePersistenceService
from app.services.repository_indexer_service import RepositoryIndexerService
from app.services.repository_services import RepositoryService
from app.services.workspace_build_service import WorkspaceBuildService


class WorkspaceBuildServiceTests(unittest.TestCase):
    def test_build_runs_in_background_and_exposes_real_stage_progress(self) -> None:
        repository_service = Mock(spec=RepositoryService)
        repository_service.extract_repo_name.return_value = "example"
        repository_service.clone_repository.side_effect = lambda _url, path: os.makedirs(path)
        repository_service.get_commit_sha.return_value = "abc123"
        repository_service.delete_repository.side_effect = lambda path: shutil.rmtree(path)
        repository_indexer = Mock(spec=RepositoryIndexerService)
        expected_metadata = RepositoryMetadata(
            repository="example",
            statistics=RepositoryStatistics(files=0, typescript=0, javascript=0),
        )

        def index_repository(*_args, progress, **_kwargs):
            for stage_id in (
                "scan",
                "documentation",
                "package",
                "parse_1",
                "parse_2",
                "parse_3",
                "relationships",
                "finalize",
            ):
                progress(stage_id, "running", None)
                progress(stage_id, "completed", None)
            return expected_metadata

        repository_indexer.index_repository_parallel.side_effect = index_repository

        with tempfile.TemporaryDirectory() as workspace_dir:
            database = Database(f"sqlite:///{os.path.join(workspace_dir, 'test.db')}")
            database.create_schema()
            persistence_service = WorkspacePersistenceService(
                database,
                LocalArtifactStore(os.path.join(workspace_dir, "artifacts")),
            )
            service = WorkspaceBuildService(
                repository_service,
                repository_indexer,
                os.path.join(workspace_dir, "checkouts"),
                persistence_service,
                max_parallel_jobs=1,
                parse_workers=3,
            )
            try:
                started_job = service.start_build("https://github.com/example/example")
                deadline = time.monotonic() + 3
                completed_job = service.get_job(started_job.jobId)
                while completed_job and completed_job.status in {"queued", "running"}:
                    if time.monotonic() > deadline:
                        self.fail("Background workspace build did not complete")
                    time.sleep(0.01)
                    completed_job = service.get_job(started_job.jobId)
            finally:
                service.shutdown()
                database.close()

            self.assertIsNotNone(completed_job)
            self.assertEqual(completed_job.status, "completed")
            self.assertEqual(completed_job.metadata.repository, "example")
            self.assertTrue(all(stage.status == "completed" for stage in completed_job.stages))
            self.assertEqual(os.listdir(os.path.join(workspace_dir, "checkouts")), [])

    def test_cleanup_failure_is_reported_and_does_not_leave_build_locked(self) -> None:
        repository_service = Mock(spec=RepositoryService)
        repository_service.extract_repo_name.return_value = "example"
        repository_service.clone_repository.side_effect = lambda _url, path: os.makedirs(path)
        repository_service.get_commit_sha.return_value = "abc123"
        repository_service.delete_repository.side_effect = OSError("checkout is locked")
        repository_indexer = Mock(spec=RepositoryIndexerService)
        repository_indexer.index_repository_parallel.return_value = RepositoryMetadata(
            repository="example",
            statistics=RepositoryStatistics(files=0, typescript=0, javascript=0),
        )

        with tempfile.TemporaryDirectory() as workspace_dir:
            database = Database(f"sqlite:///{os.path.join(workspace_dir, 'test.db')}")
            database.create_schema()
            persistence_service = WorkspacePersistenceService(
                database,
                LocalArtifactStore(os.path.join(workspace_dir, "artifacts")),
            )
            service = WorkspaceBuildService(
                repository_service,
                repository_indexer,
                os.path.join(workspace_dir, "checkouts"),
                persistence_service,
                max_parallel_jobs=1,
                parse_workers=1,
            )
            try:
                first_job = service.start_build("https://github.com/example/example")
                deadline = time.monotonic() + 3
                failed_job = service.get_job(first_job.jobId)
                while failed_job and failed_job.status != "failed":
                    if time.monotonic() > deadline:
                        self.fail("Checkout cleanup failure was not reported")
                    time.sleep(0.01)
                    failed_job = service.get_job(first_job.jobId)
                self.assertIsNotNone(failed_job)
                self.assertEqual(failed_job.status, "failed")
                self.assertIn("temporary checkout", failed_job.error)

                repository_service.delete_repository.side_effect = (
                    lambda path: shutil.rmtree(path)
                )
                second_job = service.start_build("https://github.com/example/example")
                completed_job = self._wait_for_job(service, second_job.jobId)
                self.assertEqual(completed_job.status, "completed")
            finally:
                service.shutdown()
                database.close()

    def _wait_for_job(
        self,
        service: WorkspaceBuildService,
        job_id: str,
    ):
        deadline = time.monotonic() + 3
        job = service.get_job(job_id)
        while job and job.status in {"queued", "running"}:
            if time.monotonic() > deadline:
                self.fail("Background workspace build did not complete")
            time.sleep(0.01)
            job = service.get_job(job_id)
        self.assertIsNotNone(job)
        return job


if __name__ == "__main__":
    unittest.main()
