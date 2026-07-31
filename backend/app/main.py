from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Body, Request, Header
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Literal, Optional
import os
import uuid
import asyncio
import json

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
from app.persistence.runtime_manifest_persistence_service import (
    RuntimeManifestNotFoundError,
    RuntimeManifestPersistenceService,
    RuntimeManifestRevisionConflictError,
)
from app.models.runtime_manifest_models import (
    PreviewErrorEnvelope,
    RuntimeManifestAnalyzeRequest,
    RuntimeManifestApproveRequest,
    RuntimeManifestRecord,
    RuntimeManifestUpdateRequest,
)
from app.models.preview_models import (
    PreviewCreateRequest,
    PreviewEnvironment,
    PreviewExtendRequest,
    PreviewLogs,
    PreviewStatus,
)
from app.persistence.preview_persistence_service import (
    PreviewConflictError,
    PreviewManifestNotApprovedError,
    PreviewNotFoundError,
    PreviewPersistenceService,
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
from app.services.runtime_manifest_analyzer import (
    DeterministicRuntimeManifestAnalyzer,
    StructuredAIRuntimeManifestFallback,
)
from app.services.runtime_manifest_policy import RuntimeManifestPolicy
from app.services.runtime_manifest_service import (
    RuntimeManifestPolicyError,
    RuntimeManifestService,
    RuntimeManifestWorkspaceNotReadyError,
)
from app.services.preview_logs import PreviewLogService
from app.services.preview_queue import PreviewQueueUnavailableError, RQPreviewJobQueue
from app.services.preview_service import PreviewEnvironmentValidationError, PreviewService

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="TestForge AI")


class PreviewLabAPIError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        retryable: bool = False,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}


def _correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", str(uuid.uuid4()))


@app.middleware("http")
async def attach_correlation_id(request: Request, call_next):
    request.state.correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = request.state.correlation_id
    return response


@app.exception_handler(PreviewLabAPIError)
async def handle_preview_lab_error(request: Request, exc: PreviewLabAPIError):
    envelope = PreviewErrorEnvelope(
        code=exc.code,
        message=exc.message,
        retryable=exc.retryable,
        details=exc.details,
        correlationId=_correlation_id(request),
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=envelope.model_dump(mode="json", by_alias=True),
    )


@app.exception_handler(RequestValidationError)
async def handle_request_validation(request: Request, exc: RequestValidationError):
    if "/runtime-manifest" not in request.url.path and "/previews" not in request.url.path:
        return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})
    envelope = PreviewErrorEnvelope(
        code="PREVIEW_REQUEST_INVALID",
        message="The runtime-manifest request is invalid.",
        details={"errors": jsonable_encoder(exc.errors())},
        correlationId=_correlation_id(request),
    )
    return JSONResponse(
        status_code=422,
        content=envelope.model_dump(mode="json", by_alias=True),
    )

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
runtime_manifest_persistence_service = RuntimeManifestPersistenceService(database)
runtime_manifest_service = RuntimeManifestService(
    workspace_persistence_service,
    runtime_manifest_persistence_service,
    DeterministicRuntimeManifestAnalyzer(
        fallback=(
            StructuredAIRuntimeManifestFallback(ai_provider)
            if os.getenv("RUNTIME_MANIFEST_AI_FALLBACK", "true").lower() == "true"
            else None
        ),
    ),
    RuntimeManifestPolicy(),
)
preview_persistence_service = PreviewPersistenceService(database)
preview_service = PreviewService(
    preview_persistence_service,
    RQPreviewJobQueue(),
    PreviewLogService(artifact_store),
)
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


def _raise_runtime_manifest_error(exc: Exception) -> None:
    if isinstance(exc, RuntimeManifestWorkspaceNotReadyError):
        raise PreviewLabAPIError(
            409,
            "WORKSPACE_NOT_READY",
            "The workspace must finish indexing before runtime analysis.",
            retryable=True,
        ) from exc
    if isinstance(exc, RuntimeManifestNotFoundError):
        raise PreviewLabAPIError(
            404,
            "RUNTIME_MANIFEST_NOT_FOUND",
            "No runtime manifest has been analyzed for this workspace.",
        ) from exc
    if isinstance(exc, RuntimeManifestRevisionConflictError):
        raise PreviewLabAPIError(
            409,
            "RUNTIME_MANIFEST_REVISION_CONFLICT",
            str(exc),
            retryable=True,
        ) from exc
    if isinstance(exc, RuntimeManifestPolicyError):
        raise PreviewLabAPIError(
            422,
            "RUNTIME_MANIFEST_POLICY_REJECTED",
            "The runtime manifest violates preview policy.",
            details={"violations": exc.violations},
        ) from exc
    raise PreviewLabAPIError(
        500,
        "PREVIEW_INTERNAL_ERROR",
        "The preview control plane could not complete the request.",
        retryable=False,
    ) from exc


def _raise_preview_error(exc: Exception) -> None:
    if isinstance(exc, PreviewNotFoundError):
        raise PreviewLabAPIError(404, "PREVIEW_NOT_FOUND", "The preview was not found.") from exc
    if isinstance(exc, PreviewManifestNotApprovedError):
        raise PreviewLabAPIError(409, "PREVIEW_MANIFEST_NOT_APPROVED", str(exc)) from exc
    if isinstance(exc, PreviewConflictError):
        raise PreviewLabAPIError(409, "PREVIEW_STATE_CONFLICT", str(exc), retryable=True) from exc
    if isinstance(exc, PreviewEnvironmentValidationError):
        raise PreviewLabAPIError(
            422, "PREVIEW_ENVIRONMENT_INVALID", "The preview environment is invalid.",
            details={"violations": exc.violations},
        ) from exc
    if isinstance(exc, PreviewQueueUnavailableError):
        raise PreviewLabAPIError(
            503, "PREVIEW_QUEUE_UNAVAILABLE", str(exc), retryable=True,
        ) from exc
    raise PreviewLabAPIError(
        500, "PREVIEW_INTERNAL_ERROR", "The preview control plane could not complete the request."
    ) from exc


@app.post(
    "/workspaces/{workspace_id}/runtime-manifest/analyze",
    response_model=RuntimeManifestRecord,
)
def analyze_runtime_manifest(
    workspace_id: str,
    payload: RuntimeManifestAnalyzeRequest,
):
    try:
        return runtime_manifest_service.analyze(workspace_id, payload.instructions)
    except Exception as exc:
        _raise_runtime_manifest_error(exc)


@app.get(
    "/workspaces/{workspace_id}/runtime-manifest",
    response_model=RuntimeManifestRecord,
)
def get_runtime_manifest(workspace_id: str):
    try:
        return runtime_manifest_service.get(workspace_id)
    except Exception as exc:
        _raise_runtime_manifest_error(exc)


@app.put(
    "/workspaces/{workspace_id}/runtime-manifest",
    response_model=RuntimeManifestRecord,
)
def update_runtime_manifest(
    workspace_id: str,
    payload: RuntimeManifestUpdateRequest,
):
    try:
        return runtime_manifest_service.update(
            workspace_id,
            payload.manifest,
            payload.expected_revision,
        )
    except Exception as exc:
        _raise_runtime_manifest_error(exc)


@app.post(
    "/workspaces/{workspace_id}/runtime-manifest/approve",
    response_model=RuntimeManifestRecord,
)
def approve_runtime_manifest(
    workspace_id: str,
    payload: RuntimeManifestApproveRequest,
):
    try:
        return runtime_manifest_service.approve(
            workspace_id,
            payload.expected_revision,
        )
    except Exception as exc:
        _raise_runtime_manifest_error(exc)


@app.post(
    "/workspaces/{workspace_id}/previews",
    response_model=PreviewEnvironment,
    status_code=202,
)
def create_preview(
    workspace_id: str,
    payload: PreviewCreateRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
):
    try:
        return preview_service.create(workspace_id, idempotency_key, payload)
    except Exception as exc:
        _raise_preview_error(exc)


@app.get("/previews/{preview_id}", response_model=PreviewEnvironment)
def get_preview(preview_id: str):
    try:
        return preview_service.get(preview_id)
    except Exception as exc:
        _raise_preview_error(exc)


@app.get("/workspaces/{workspace_id}/previews/latest", response_model=PreviewEnvironment)
def get_latest_preview(workspace_id: str):
    try:
        return preview_service.latest_for_workspace(workspace_id)
    except Exception as exc:
        _raise_preview_error(exc)


@app.get("/previews/{preview_id}/logs", response_model=PreviewLogs)
def get_preview_logs(preview_id: str):
    try:
        return preview_service.logs_for(preview_id)
    except Exception as exc:
        _raise_preview_error(exc)


@app.get("/previews/{preview_id}/events")
async def stream_preview_events(preview_id: str, request: Request):
    try:
        preview_service.get(preview_id)
    except Exception as exc:
        _raise_preview_error(exc)

    async def event_stream():
        seen: set[str] = set()
        while not await request.is_disconnected():
            events = preview_persistence_service.events(preview_id)
            for event in events:
                if event.id in seen:
                    continue
                seen.add(event.id)
                payload = json.dumps(event.model_dump(mode="json", by_alias=True))
                yield f"id: {event.id}\nevent: preview-status\ndata: {payload}\n\n"
            yield ": keep-alive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/previews/{preview_id}/stop", response_model=PreviewEnvironment, status_code=202)
def stop_preview(
    preview_id: str,
    idempotency_key: str = Header(alias="Idempotency-Key"),
):
    del idempotency_key
    try:
        return preview_service.stop(preview_id)
    except Exception as exc:
        _raise_preview_error(exc)


@app.post("/previews/{preview_id}/extend", response_model=PreviewEnvironment)
def extend_preview(
    preview_id: str,
    payload: PreviewExtendRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
):
    del idempotency_key
    try:
        return preview_service.extend(preview_id, payload)
    except Exception as exc:
        _raise_preview_error(exc)


@app.delete("/workspaces/{workspace_id}", status_code=204)
def delete_workspace(workspace_id: str):
    try:
        active_previews = preview_persistence_service.active_for_workspace(workspace_id)
        if active_previews:
            for preview in active_previews:
                preview_service.stop(preview.id)
            raise HTTPException(
                status_code=409,
                detail="Preview cleanup was queued. Remove the workspace after its previews stop.",
            )
        preview_ids = preview_persistence_service.ids_for_workspace(workspace_id)
        for preview_id in preview_ids:
            artifact_store.delete(PreviewLogService.key(preview_id))
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
