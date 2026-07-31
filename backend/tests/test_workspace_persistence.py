import os
import tempfile
import unittest

from app.models.code_models import (
    CodeClass,
    GraphRelationship,
    ParsedFile,
    ParsedFileSummary,
    RepositoryMetadata,
    RepositoryStatistics,
    WorkspaceBuildJob,
    WorkspaceBuildStage,
)
from app.persistence.artifact_codec import RepositoryArtifactCodec
from app.persistence.artifact_store import LocalArtifactStore
from app.persistence.database import Database
from app.persistence.workspace_persistence_service import (
    WorkspaceBuildInProgressError,
    WorkspacePersistenceService,
)


def create_metadata() -> RepositoryMetadata:
    return RepositoryMetadata(
        repository="example",
        statistics=RepositoryStatistics(files=1, typescript=1, javascript=0),
        parsedFiles=[
            ParsedFileSummary(
                path="src/example.ts",
                classes=1,
                functions=0,
                imports=0,
                existing_tests=0,
            )
        ],
        parsed_file_details=[
            ParsedFile(
                path="src/example.ts",
                file="example.ts",
                source_code="export class Example {}",
                classes=[CodeClass(name="Example")],
            )
        ],
        relationships=[
            GraphRelationship(
                source="src/example.ts",
                target="src/dependency.ts",
                module="./dependency",
                kind="local",
            )
        ],
    )


class RepositoryArtifactCodecTests(unittest.TestCase):
    def test_round_trip_preserves_excluded_parsed_source_details(self) -> None:
        codec = RepositoryArtifactCodec()
        encoded = codec.encode("workspace-id", "abc123", create_metadata())

        restored = codec.decode(encoded.contents, encoded.checksum_sha256)

        self.assertEqual(restored.parsed_file_details[0].source_code, "export class Example {}")
        self.assertEqual(restored.parsed_file_details[0].classes[0].name, "Example")

    def test_checksum_mismatch_is_rejected(self) -> None:
        codec = RepositoryArtifactCodec()
        encoded = codec.encode("workspace-id", "abc123", create_metadata())

        with self.assertRaisesRegex(RuntimeError, "checksum"):
            codec.decode(encoded.contents, "0" * 64)


class WorkspacePersistenceServiceTests(unittest.TestCase):
    def test_workspace_cannot_be_deleted_during_build(self) -> None:
        with tempfile.TemporaryDirectory() as data_dir:
            database = Database(f"sqlite:///{os.path.join(data_dir, 'test.db')}")
            database.create_schema()
            service = WorkspacePersistenceService(
                database,
                LocalArtifactStore(os.path.join(data_dir, "artifacts")),
            )
            workspace = service.create_workspace(
                "https://github.com/example/example",
                "example",
            )

            with self.assertRaisesRegex(WorkspaceBuildInProgressError, "in progress"):
                service.delete_workspace(workspace.id)

            self.assertEqual(len(service.list_workspaces()), 1)
            database.close()

    def test_completed_workspace_survives_new_service_instance_and_can_be_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as data_dir:
            database_url = f"sqlite:///{os.path.join(data_dir, 'test.db')}"
            artifact_root = os.path.join(data_dir, "artifacts")
            database = Database(database_url)
            database.create_schema()
            service = WorkspacePersistenceService(
                database,
                LocalArtifactStore(artifact_root),
            )
            workspace = service.create_workspace(
                "https://github.com/example/example",
                "example",
            )
            stages = [
                WorkspaceBuildStage(
                    id="finalize",
                    label="Finalize",
                    detail="Done",
                    status="completed",
                )
            ]
            job = WorkspaceBuildJob(
                jobId="job-id",
                workspaceId=workspace.id,
                status="completed",
                stages=stages,
            )
            service.create_build(job)
            service.complete_build(job, create_metadata(), "abc123")

            restarted_database = Database(database_url)
            restarted_service = WorkspacePersistenceService(
                restarted_database,
                LocalArtifactStore(artifact_root),
            )
            summaries = restarted_service.list_workspaces()
            restored = restarted_service.load_metadata(workspace.id)

            self.assertEqual(len(summaries), 1)
            self.assertEqual(summaries[0].status, "ready")
            self.assertEqual(restored.parsed_file_details[0].source_code, "export class Example {}")
            self.assertTrue(restarted_service.delete_workspace(workspace.id))
            self.assertEqual(restarted_service.list_workspaces(), [])
            remaining_artifacts = [
                path
                for path, _, files in os.walk(artifact_root)
                for file_name in files
                for path in [os.path.join(path, file_name)]
            ]
            self.assertEqual(remaining_artifacts, [])
            restarted_database.close()
            database.close()


if __name__ == "__main__":
    unittest.main()
