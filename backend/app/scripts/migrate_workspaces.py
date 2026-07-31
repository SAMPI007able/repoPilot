import argparse
import os
import uuid
from pathlib import Path

from app.models.code_models import WorkspaceBuildJob, WorkspaceBuildStage
from app.persistence.artifact_store import create_artifact_store
from app.persistence.database import Database
from app.persistence.workspace_persistence_service import WorkspacePersistenceService
from app.services.graph_services import GraphService
from app.services.parser_services import ParserService
from app.services.repository_indexer_service import RepositoryIndexerService
from app.services.repository_services import RepositoryService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Persist legacy cloned workspaces as compressed repository-index artifacts."
    )
    parser.add_argument(
        "--repositories-dir",
        help="Legacy repository directory. Defaults to backend/workspace/repositories.",
    )
    parser.add_argument(
        "--delete-after-persist",
        action="store_true",
        help="Delete each clone only after upload and checksum verification succeed.",
    )
    parser.add_argument(
        "--parse-workers",
        type=int,
        default=int(os.getenv("WORKSPACE_PARSE_WORKERS", "3")),
    )
    return parser


def main() -> None:
    arguments = build_parser().parse_args()
    backend_dir = Path(__file__).resolve().parents[2]
    persistence_dir = backend_dir / "workspace"
    repositories_dir = arguments.repositories_dir or os.path.join(
        str(persistence_dir), "repositories"
    )
    database_path = os.path.join(str(persistence_dir), "testforge.db").replace("\\", "/")
    database = Database(os.getenv("DATABASE_URL", f"sqlite:///{database_path}"))
    database.create_schema()
    artifact_store = create_artifact_store(os.path.join(str(persistence_dir), "artifacts"))
    persistence = WorkspacePersistenceService(database, artifact_store)
    repository_service = RepositoryService()
    indexer = RepositoryIndexerService(
        repository_service,
        ParserService(),
        GraphService(),
    )

    try:
        repository_paths = [
            os.path.join(repositories_dir, directory_name)
            for directory_name in os.listdir(repositories_dir)
            if os.path.isdir(os.path.join(repositories_dir, directory_name))
        ] if os.path.isdir(repositories_dir) else []

        if not repository_paths:
            print(f"No legacy repositories found under {repositories_dir}")
            return

        for repository_path in repository_paths:
            migrate_repository(
                repository_path,
                persistence,
                repository_service,
                indexer,
                arguments.parse_workers,
                arguments.delete_after_persist,
            )
    finally:
        database.close()


def migrate_repository(
    repository_path: str,
    persistence: WorkspacePersistenceService,
    repository_service: RepositoryService,
    indexer: RepositoryIndexerService,
    parse_workers: int,
    delete_after_persist: bool,
) -> None:
    repository_name = os.path.basename(repository_path)
    try:
        import git

        repository = git.Repo(repository_path)
        repo_url = repository.remotes.origin.url
    except Exception as exc:
        print(f"Skipping {repository_name}: unable to read Git origin ({exc})")
        return

    print(f"Indexing legacy workspace {repository_name}...")
    workspace = persistence.create_workspace(repo_url, repository_name)
    stage = WorkspaceBuildStage(
        id="legacy_migration",
        label="Legacy workspace migration",
        detail="Persisting existing repository checkout",
        status="running",
    )
    job = WorkspaceBuildJob(
        jobId=uuid.uuid4().hex,
        workspaceId=workspace.id,
        status="running",
        stages=[stage],
    )
    persistence.create_build(job)

    try:
        metadata = indexer.index_repository_parallel(
            repository_name,
            repository_path,
            parse_workers=parse_workers,
        )
        commit_sha = repository_service.get_commit_sha(repository_path)
        stage.status = "completed"
        job.status = "completed"
        persistence.complete_build(job, metadata, commit_sha)
        if persistence.load_metadata(workspace.id) is None:
            raise RuntimeError("Persisted artifact could not be restored.")

        print(f"Persisted {repository_name} as workspace {workspace.id}")
        if delete_after_persist:
            repository_service.delete_repository(repository_path)
            print(f"Removed checkout {repository_path}")
    except Exception as exc:
        stage.status = "failed"
        job.status = "failed"
        job.error = str(exc)
        persistence.fail_build(job)
        print(f"Failed to migrate {repository_name}: {exc}")


if __name__ == "__main__":
    main()
