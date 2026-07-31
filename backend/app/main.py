from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Body
from pydantic import BaseModel
from typing import Literal, Optional
import os

from app.models.code_models import (
    ImpactAnalysisResult,
    RepositoryMetadata,
    WorkspaceBuildJob,
    WorkspaceDetail,
    WorkspaceSummary,
)
from app.persistence.artifact_store import create_artifact_store
from app.persistence.database import Database
from app.persistence.workspace_persistence_service import (
    WorkspaceBuildInProgressError,
    WorkspacePersistenceService,
)
from app.services.ai.ai_service import AIService
from app.services.ai.chat_capability import ChatCapability
from app.services.ai.documentation_capability import DocumentationCapability
from app.services.ai.gemini_provider import GeminiProvider
from app.services.ai.provider import AIProviderUnavailableError
from app.services.ai.test_generation_capability import TestGenerationCapability
from app.services.chat_prompt_builder_service import ChatPromptBuilderService
from app.services.context_builder_service import ContextBuilderService
from app.services.documentation_prompt_builder_service import DocumentationPromptBuilderService
from app.services.graph_services import GraphService
from app.services.impact_analysis_service import ImpactAnalysisService
from app.services.prompt_builder_service import PromptBuilderService
from app.services.repository_services import RepositoryService
from app.services.parser_services import ParserService
from app.services.repository_indexer_service import RepositoryIndexerService
from app.services.workspace_build_service import (
    WorkspaceBuildAlreadyRunningError,
    WorkspaceBuildService,
)

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="TestForge AI")

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Services ────────────────────────────────────────────────────────────────
repo_service = RepositoryService()
parser_service = ParserService()
graph_service = GraphService()
repository_indexer = RepositoryIndexerService(repo_service, parser_service, graph_service)
context_builder_service = ContextBuilderService(graph_service)
prompt_builder_service = PromptBuilderService()
impact_analysis_service = ImpactAnalysisService()
chat_prompt_builder_service = ChatPromptBuilderService()
documentation_prompt_builder_service = DocumentationPromptBuilderService()
ai_provider = GeminiProvider()
chat_capability = ChatCapability(ai_provider, chat_prompt_builder_service)
test_generation_capability = TestGenerationCapability(ai_provider, context_builder_service, prompt_builder_service)
documentation_capability = DocumentationCapability(ai_provider, documentation_prompt_builder_service)
ai_service = AIService(chat_capability, test_generation_capability, documentation_capability)

# ── Workspace directory ──────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PERSISTENCE_DIR = os.path.join(BASE_DIR, "workspace")
WORKSPACE_DIR = os.path.join(PERSISTENCE_DIR, "checkouts")
os.makedirs(WORKSPACE_DIR, exist_ok=True)
default_database_path = os.path.join(PERSISTENCE_DIR, "testforge.db").replace("\\", "/")
database = Database(os.getenv("DATABASE_URL", f"sqlite:///{default_database_path}"))
database.create_schema()
artifact_store = create_artifact_store(os.path.join(PERSISTENCE_DIR, "artifacts"))
workspace_persistence_service = WorkspacePersistenceService(database, artifact_store)
workspace_persistence_service.mark_interrupted_builds_failed()
workspace_build_service = WorkspaceBuildService(
    repo_service,
    repository_indexer,
    WORKSPACE_DIR,
    workspace_persistence_service,
    max_parallel_jobs=int(os.getenv("WORKSPACE_BUILD_JOBS", "1")),
    parse_workers=int(os.getenv("WORKSPACE_PARSE_WORKERS", "3")),
)


@app.on_event("shutdown")
def shutdown_workspace_builds() -> None:
    workspace_build_service.shutdown()
    database.close()


# ── Request / Response models ────────────────────────────────────────────────
class IndexRequest(BaseModel):
    githubUrl: str


class QueryRequest(BaseModel):
    """
    Unified AI query request.

    type = "chat"
        • query  — the free-form codebase question
        • workspaceId — the indexed repository to query against

    type = "test_generation"
        • workspaceId — the indexed repository
        • generationMode — "file" or "scenario" (defaults to "file")
        • target      — required only for file mode
        • scenario    — requirement/behavior text required only for scenario mode
        • testType    — e.g. "unit", "integration", "e2e"
    """
    type: Literal["chat", "test_generation"]
    workspaceId: str
    query: Optional[str] = None      # used by chat
    target: Optional[str] = None     # used by test_generation
    scenario: Optional[str] = None   # used by scenario-based test_generation
    generationMode: Literal["file", "scenario"] = "file"
    testType: Optional[str] = None   # used by test_generation


class QueryResponse(BaseModel):
    type: str
    workspaceId: str
    prompt: str
    markdown: str
    # Optional — only present for test_generation
    target: Optional[str] = None
    testType: Optional[str] = None


class ImpactAnalysisRequest(BaseModel):
    workspaceId: str
    target: str


# ── Legacy request/response (kept for backward compat) ───────────────────────
class GenerateTestsRequest(BaseModel):
    workspaceId: str
    target: str
    type: str


class GenerateTestsResponse(BaseModel):
    workspaceId: str
    target: str
    type: str
    prompt: str
    markdown: str


# ── Helpers ──────────────────────────────────────────────────────────────────
def _load_workspace(workspace_id: str) -> tuple[str, RepositoryMetadata]:
    metadata = workspace_build_service.get_completed_metadata(workspace_id)
    if metadata is None:
        raise HTTPException(
            status_code=404,
            detail=f"Persisted workspace '{workspace_id}' was not found or is not ready.",
        )
    return "", metadata


# ── Routes ───────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/workspaces/index", response_model=WorkspaceBuildJob, status_code=202)
def index_workspace(
    githubUrl: str | None = Form(None),
    project_docs: list[UploadFile] | None = File(default=None),
    payload: IndexRequest | None = Body(None),
):
    git_url = githubUrl or (payload.githubUrl if payload else None)
    if not git_url:
        raise HTTPException(status_code=400, detail="githubUrl is required")

    try:
        documents = [
            (upload.filename or "project-document", upload.file.read())
            for upload in (project_docs or [])
        ]
        return workspace_build_service.start_build(git_url, documents)
    except WorkspaceBuildAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start workspace build: {str(e)}")


@app.get("/workspaces/index/{job_id}", response_model=WorkspaceBuildJob)
def get_workspace_build(job_id: str):
    job = workspace_build_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Workspace build job '{job_id}' was not found.")
    return job


@app.get("/workspaces", response_model=list[WorkspaceSummary])
def list_workspaces():
    return workspace_build_service.list_workspaces()


@app.get("/workspaces/{workspace_id}", response_model=WorkspaceDetail)
def get_workspace(workspace_id: str):
    workspace = workspace_build_service.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"Workspace '{workspace_id}' was not found.")
    return workspace


@app.delete("/workspaces/{workspace_id}", status_code=204)
def delete_workspace(workspace_id: str):
    try:
        if not workspace_build_service.delete_workspace(workspace_id):
            raise HTTPException(
                status_code=404,
                detail=f"Workspace '{workspace_id}' was not found.",
            )
    except WorkspaceBuildInProgressError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/ai/query", response_model=QueryResponse)
def ai_query(payload: QueryRequest):
    """
    Unified AI query endpoint.

    Supported types:
    - "chat"             → free-form codebase question
    - "test_generation"  → generate tests for a target file/class
    """
    try:
        _, repository_metadata = _load_workspace(payload.workspaceId)

        if payload.type == "chat":
            if not payload.query:
                raise HTTPException(status_code=400, detail="query is required for type=chat")

            prompt, markdown = ai_service.chat(repository_metadata, payload.query)
            return QueryResponse(
                type="chat",
                workspaceId=payload.workspaceId,
                prompt=prompt,
                markdown=markdown,
            )

        elif payload.type == "test_generation":
            test_type = payload.testType or "unit"
            if payload.generationMode == "scenario":
                if not payload.scenario or not payload.scenario.strip():
                    raise HTTPException(
                        status_code=400,
                        detail="scenario is required for scenario test generation",
                    )
                prompt, markdown = ai_service.generate_tests_from_scenario(
                    repository_metadata,
                    payload.scenario.strip(),
                    test_type,
                )
            else:
                if not payload.target:
                    raise HTTPException(
                        status_code=400,
                        detail="target is required for file test generation",
                    )
                prompt, markdown = ai_service.generate_tests(
                    repository_metadata,
                    payload.target,
                    test_type,
                )

            return QueryResponse(
                type="test_generation",
                workspaceId=payload.workspaceId,
                prompt=prompt,
                markdown=markdown,
                target=payload.target or payload.scenario,
                testType=test_type,
            )

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported query type: {payload.type}")

    except HTTPException:
        raise
    except AIProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI query failed: {str(exc)}") from exc


@app.post("/ai/generate-tests", response_model=GenerateTestsResponse, deprecated=True)
def generate_tests(payload: GenerateTestsRequest):
    """Deprecated — use POST /ai/query with type=test_generation instead."""
    try:
        _, repository_metadata = _load_workspace(payload.workspaceId)
        prompt, markdown = ai_service.generate_tests(repository_metadata, payload.target, payload.type)

        return GenerateTestsResponse(
            workspaceId=payload.workspaceId,
            target=payload.target,
            type=payload.type,
            prompt=prompt,
            markdown=markdown,
        )
    except HTTPException:
        raise
    except AIProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate tests: {str(exc)}") from exc


@app.post("/workspaces/impact-analysis", response_model=ImpactAnalysisResult)
def impact_analysis(payload: ImpactAnalysisRequest):
    try:
        _, repository_metadata = _load_workspace(payload.workspaceId)
        return impact_analysis_service.analyze(repository_metadata, payload.target)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Impact analysis failed: {str(exc)}") from exc
