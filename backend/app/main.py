from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Body, Request, Header, Depends, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse, RedirectResponse
from pydantic import BaseModel
from typing import Literal, Optional
import os
import uuid
import asyncio
import json
import hashlib

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
from app.models.identity_models import CurrentUserResponse, Principal
from app.models.integration_models import (
    ImportRepositoryRequest, OAuthConnectResponse, ProviderConnection,
    ProviderRepository, RepositoryContent,
)
from app.persistence.identity_persistence_service import IdentityPersistenceService
from app.services.auth_dependencies import AuthenticationDependencies
from app.services.authentication import AuthenticationError, create_token_verifier
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
from app.persistence.oauth_persistence_service import OAuthPersistenceService
from app.persistence.feature_flag_persistence_service import (
    FeatureFlagNotFoundError,
    FeatureFlagPersistenceService,
)
from app.models.feature_flag_models import (
    FeatureFlagRecord,
    FeatureFlagsResponse,
    FeatureFlagUpdateRequest,
)
from app.services.oauth_integrations import IntegrationError, OAuthIntegrationService
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
from app.config.rate_limit_settings import RateLimitSettings
from app.services.rate_limit_guard import QuotaAPIError, RateLimitDecision, RateLimitGuard
from app.services.rate_limit_service import RateLimitBackendUnavailable, RateLimitService
from app.services.telemetry import Telemetry

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="TestForge AI")
telemetry = Telemetry()


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
    response.headers.setdefault("Cache-Control", "no-store")
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


@app.exception_handler(AuthenticationError)
async def handle_authentication_error(request: Request, exc: AuthenticationError):
    envelope = PreviewErrorEnvelope(
        code=exc.code, message=exc.message, retryable=exc.retryable,
        details={}, correlationId=_correlation_id(request),
    )
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return JSONResponse(
        status_code=exc.status_code,
        content=envelope.model_dump(mode="json", by_alias=True),
        headers=headers,
    )


@app.exception_handler(QuotaAPIError)
async def handle_quota_error(request: Request, exc: QuotaAPIError):
    envelope = PreviewErrorEnvelope(
        code=exc.code, message=exc.message, retryable=True,
        details=exc.details, correlationId=_correlation_id(request),
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=envelope.model_dump(mode="json", by_alias=True),
        headers=exc.headers,
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
feature_flag_service = FeatureFlagPersistenceService(database)
feature_flag_service.ensure_defaults()
identity_persistence_service = IdentityPersistenceService(database)
oauth_persistence_service = OAuthPersistenceService(database)
oauth_integration_service = OAuthIntegrationService(oauth_persistence_service)
auth = AuthenticationDependencies(identity_persistence_service, create_token_verifier())
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
rate_limit_settings = RateLimitSettings.from_env()
rate_limit_service = RateLimitService(rate_limit_settings)
rate_limit_guard = RateLimitGuard(rate_limit_service, rate_limit_settings)
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
def _load_workspace(workspace_id: str, principal: Principal) -> tuple[str, RepositoryMetadata]:
    if not workspace_persistence_service.owns_workspace(workspace_id, principal.user_id):
        raise HTTPException(status_code=404, detail=f"Workspace '{workspace_id}' was not found.")
    metadata = workspace_build_service.get_completed_metadata(workspace_id)
    if metadata is None:
        raise HTTPException(
            status_code=404,
            detail=f"Persisted workspace '{workspace_id}' was not found or is not ready.",
        )
    return "", metadata


def _authorize_workspace(workspace_id: str, principal: Principal) -> None:
    if not workspace_persistence_service.owns_workspace(workspace_id, principal.user_id):
        raise HTTPException(status_code=404, detail=f"Workspace '{workspace_id}' was not found.")


def _authorize_preview(preview_id: str, principal: Principal) -> None:
    if not preview_persistence_service.is_owned_by(preview_id, principal.user_id):
        raise PreviewLabAPIError(404, "PREVIEW_NOT_FOUND", "The preview was not found.")


def _require_feature(key: str) -> None:
    if not feature_flag_service.is_enabled(key):
        raise PreviewLabAPIError(
            503,
            "FEATURE_DISABLED",
            f"The '{key}' feature is currently disabled.",
            details={"feature": key},
        )


def _apply_rate_headers(response: Response, decision: RateLimitDecision) -> None:
    for name, value in decision.headers.items():
        response.headers[name] = value


def _preview_reservation_id(workspace_id: str, idempotency_key: str) -> str:
    value = f"{workspace_id}:{idempotency_key}".encode("utf-8")
    return f"reservation:{hashlib.sha256(value).hexdigest()[:32]}"


# ── Routes ───────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/feature-flags", response_model=FeatureFlagsResponse)
def get_feature_flags():
    return FeatureFlagsResponse(flags=feature_flag_service.client_flags())


@app.get("/me", response_model=CurrentUserResponse)
def get_me(principal: Principal = Depends(auth.principal)):
    user = identity_persistence_service.current_user(principal.user_id)
    telemetry.identify(principal.user_id, {
        "email": user.primary_email,
        "display_name": user.display_name
    })
    telemetry.capture(principal.user_id, "user_registered", {"source": "backend_me"})
    return user


@app.get("/integrations", response_model=list[ProviderConnection])
def list_integrations(principal: Principal = Depends(auth.active_principal)):
    return oauth_integration_service.statuses(principal.user_id)


@app.get("/integrations/{provider}/connect", response_model=OAuthConnectResponse)
def connect_integration(provider: str, principal: Principal = Depends(auth.active_principal)):
    try:
        return OAuthConnectResponse(authorizationUrl=oauth_integration_service.authorization_url(provider, principal.user_id))
    except IntegrationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/integrations/{provider}/callback")
def integration_callback(provider: str, code: str | None = None, state: str | None = None, error: str | None = None):
    if error:
        return RedirectResponse(f"{oauth_integration_service.frontend_url}/repositories?integration={provider}&status=denied")
    if not code or not state:
        raise HTTPException(status_code=400, detail="OAuth callback code and state are required.")
    try:
        return RedirectResponse(oauth_integration_service.complete_callback(provider, code, state), status_code=303)
    except IntegrationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.delete("/integrations/{provider}", status_code=204)
def disconnect_integration(provider: str, principal: Principal = Depends(auth.active_principal)):
    oauth_integration_service.disconnect(principal.user_id, provider)
    return Response(status_code=204)


@app.get("/integrations/{provider}/repos", response_model=list[ProviderRepository])
def list_integration_repositories(provider: str, principal: Principal = Depends(auth.active_principal)):
    try:
        return oauth_integration_service.repositories(principal.user_id, provider)
    except IntegrationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/integrations/{provider}/repos/{owner}/{repo}/contents/{path:path}", response_model=RepositoryContent)
def get_integration_repository_content(provider: str, owner: str, repo: str, path: str, ref: str | None = None, principal: Principal = Depends(auth.active_principal)):
    try:
        return oauth_integration_service.content(principal.user_id, provider, owner, repo, path, ref)
    except IntegrationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/integrations/{provider}/repos/import", response_model=WorkspaceBuildJob, status_code=202)
def import_integration_repository(
    provider: str, payload: ImportRepositoryRequest, response: Response,
    principal: Principal = Depends(auth.active_principal),
):
    try:
        repository = oauth_integration_service.repository(principal.user_id, provider, payload.owner, payload.repo)
        token = oauth_integration_service.access_token(principal.user_id, provider)
        _apply_rate_headers(response, rate_limit_guard.enforce(principal, "repository_index"))
        telemetry.capture(principal.user_id, "repo_connected", {
            "source": "integration_import",
            "provider": provider,
            "repository_url": repository.clone_url,
            "repository_owner": payload.owner,
            "repository_name": payload.repo,
        })
        workspace = workspace_build_service.start_build(
            repository.clone_url, owner_user_id=principal.user_id,
            clone_authorization=token, trusted_provider_url=True,
        )
        telemetry.capture(principal.user_id, "repo_indexed", {
            "source": "integration_import",
            "workspace_id": workspace.workspaceId,
            "provider": provider,
            "repository_url": repository.clone_url,
            "repository_owner": payload.owner,
            "repository_name": payload.repo,
        })
        return workspace
    except IntegrationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/workspaces/index", response_model=WorkspaceBuildJob, status_code=202)
def index_workspace(
    response: Response,
    githubUrl: str | None = Form(None),
    project_docs: list[UploadFile] | None = File(default=None),
    payload: IndexRequest | None = Body(None),
    principal: Principal = Depends(auth.active_principal),
):
    git_url = githubUrl or (payload.githubUrl if payload else None)
    if not git_url:
        raise HTTPException(status_code=400, detail="githubUrl is required")

    try:
        if project_docs:
            _apply_rate_headers(response, rate_limit_guard.enforce(principal, "document_upload"))
        _apply_rate_headers(response, rate_limit_guard.enforce(principal, "repository_index"))
        documents = [
            (upload.filename or "project-document", upload.file.read())
            for upload in (project_docs or [])
        ]
        if project_docs:
            telemetry.capture(principal.user_id, "document_uploaded", {
                "source": "workspace_index",
                "repository_url": git_url,
                "document_count": len(project_docs),
            })
        workspace = workspace_build_service.start_build(
            git_url, documents, owner_user_id=principal.user_id
        )
        telemetry.capture(principal.user_id, "repo_connected", {"source": "workspace_index", "repository_url": git_url})
        telemetry.capture(principal.user_id, "repo_indexed", {"source": "workspace_index", "workspace_id": workspace.workspaceId})
        return workspace
    except QuotaAPIError:
        raise
    except WorkspaceBuildAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start workspace build: {str(e)}")


@app.get("/workspaces/index/{job_id}", response_model=WorkspaceBuildJob)
def get_workspace_build(job_id: str, principal: Principal = Depends(auth.active_principal)):
    job = workspace_build_service.get_job(job_id, principal.user_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Workspace build job '{job_id}' was not found.")
    return job


@app.get("/workspaces", response_model=list[WorkspaceSummary])
def list_workspaces(principal: Principal = Depends(auth.active_principal)):
    return workspace_build_service.list_workspaces(principal.user_id)


@app.get("/workspaces/{workspace_id}", response_model=WorkspaceDetail)
def get_workspace(workspace_id: str, principal: Principal = Depends(auth.active_principal)):
    workspace = workspace_build_service.get_workspace(workspace_id, principal.user_id)
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
    principal: Principal = Depends(auth.active_principal),
):
    _authorize_workspace(workspace_id, principal)
    try:
        return runtime_manifest_service.analyze(workspace_id, payload.instructions)
    except Exception as exc:
        _raise_runtime_manifest_error(exc)


@app.get(
    "/workspaces/{workspace_id}/runtime-manifest",
    response_model=RuntimeManifestRecord,
)
def get_runtime_manifest(workspace_id: str, principal: Principal = Depends(auth.active_principal)):
    _authorize_workspace(workspace_id, principal)
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
    principal: Principal = Depends(auth.active_principal),
):
    _authorize_workspace(workspace_id, principal)
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
    principal: Principal = Depends(auth.active_principal),
):
    _authorize_workspace(workspace_id, principal)
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
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    principal: Principal = Depends(auth.active_principal),
):
    _authorize_workspace(workspace_id, principal)
    _require_feature("preview")
    if not idempotency_key or len(idempotency_key) > 128:
        raise PreviewLabAPIError(
            422, "PREVIEW_ENVIRONMENT_INVALID", "The preview environment is invalid.",
            details={"violations": ["Idempotency-Key must contain 1 to 128 characters."]},
        )
    existing = preview_persistence_service.find_by_idempotency(workspace_id, idempotency_key)
    if existing is not None:
        return existing
    try:
        rate_limit_service.reconcile_concurrency(
            principal.user_id, "preview", preview_persistence_service.active_ids_for_user(principal.user_id),
        )
    except RateLimitBackendUnavailable as exc:
        raise QuotaAPIError(
            503, "RATE_LIMIT_UNAVAILABLE", "The resource quota service is temporarily unavailable.",
            {"resource": "preview"}, {"Retry-After": "30"},
        ) from exc
    decision = rate_limit_guard.enforce(principal, "preview_creation", fail_closed=True)
    _apply_rate_headers(response, decision)
    reservation_id = _preview_reservation_id(workspace_id, idempotency_key)
    rate_limit_guard.acquire(principal, "preview", reservation_id)
    try:
        preview = preview_service.create(workspace_id, idempotency_key, payload)
        try:
            rate_limit_service.replace_concurrency_slot(
                principal.user_id, "preview", reservation_id, preview.id,
            )
            telemetry.capture(principal.user_id, "preview_started", {
                "workspace_id": workspace_id,
                "preview_id": preview.id,
                "environment_count": len(payload.environment or {}),
            })
        except RateLimitBackendUnavailable:
            # The reservation still counts this preview; the next create request reconciles exact IDs.
            pass
        return preview
    except Exception as exc:
        try:
            rate_limit_service.release_concurrency_slot(principal.user_id, "preview", reservation_id)
        except RateLimitBackendUnavailable:
            pass
        telemetry.capture(principal.user_id, "preview_failed", {
            "workspace_id": workspace_id,
            "idempotency_key": idempotency_key,
            "error": str(exc),
        })
        _raise_preview_error(exc)


@app.get("/previews/{preview_id}", response_model=PreviewEnvironment)
def get_preview(preview_id: str, principal: Principal = Depends(auth.active_principal)):
    _authorize_preview(preview_id, principal)
    try:
        return preview_service.get(preview_id)
    except Exception as exc:
        _raise_preview_error(exc)


@app.get("/workspaces/{workspace_id}/previews/latest", response_model=PreviewEnvironment)
def get_latest_preview(workspace_id: str, principal: Principal = Depends(auth.active_principal)):
    _authorize_workspace(workspace_id, principal)
    try:
        return preview_service.latest_for_workspace(workspace_id)
    except Exception as exc:
        _raise_preview_error(exc)


@app.get("/previews/{preview_id}/logs", response_model=PreviewLogs)
def get_preview_logs(preview_id: str, principal: Principal = Depends(auth.active_principal)):
    _authorize_preview(preview_id, principal)
    try:
        return preview_service.logs_for(preview_id)
    except Exception as exc:
        _raise_preview_error(exc)


@app.get("/previews/{preview_id}/events")
async def stream_preview_events(
    preview_id: str, request: Request,
    principal: Principal = Depends(auth.active_principal),
):
    _authorize_preview(preview_id, principal)
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
    principal: Principal = Depends(auth.active_principal),
):
    del idempotency_key
    _authorize_preview(preview_id, principal)
    try:
        preview = preview_service.stop(preview_id)
        try:
            rate_limit_service.release_concurrency_slot(principal.user_id, "preview", preview_id)
            telemetry.capture(principal.user_id, "preview_completed", {"preview_id": preview_id, "status": preview.status.value})
        except RateLimitBackendUnavailable:
            pass
        return preview
    except Exception as exc:
        _raise_preview_error(exc)


@app.post("/previews/{preview_id}/extend", response_model=PreviewEnvironment)
def extend_preview(
    preview_id: str,
    payload: PreviewExtendRequest,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    principal: Principal = Depends(auth.active_principal),
):
    del idempotency_key
    _authorize_preview(preview_id, principal)
    _require_feature("preview")
    try:
        _apply_rate_headers(response, rate_limit_guard.enforce(principal, "preview_extension", fail_closed=True))
        preview = preview_service.extend(preview_id, payload)
        telemetry.capture(principal.user_id, "preview_started", {"preview_id": preview_id, "extended": True})
        return preview
    except QuotaAPIError:
        raise
    except Exception as exc:
        _raise_preview_error(exc)


@app.delete("/workspaces/{workspace_id}", status_code=204)
def delete_workspace(workspace_id: str, principal: Principal = Depends(auth.active_principal)):
    _authorize_workspace(workspace_id, principal)
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
        if not workspace_build_service.delete_workspace(workspace_id, principal.user_id):
            raise HTTPException(
                status_code=404,
                detail=f"Workspace '{workspace_id}' was not found.",
            )
    except WorkspaceBuildInProgressError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/ai/query", response_model=QueryResponse)
def ai_query(payload: QueryRequest, response: Response, principal: Principal = Depends(auth.active_principal)):
    """
    Unified AI query endpoint.

    Supported types:
    - "chat"             → free-form codebase question
    - "test_generation"  → generate tests for a target file/class
    """
    try:
        _, repository_metadata = _load_workspace(payload.workspaceId, principal)

        if payload.type == "chat":
            if not payload.query:
                raise HTTPException(status_code=400, detail="query is required for type=chat")

            _apply_rate_headers(response, rate_limit_guard.enforce(principal, "project_chat"))
            prompt, markdown = ai_service.chat(repository_metadata, payload.query)
            telemetry.capture(principal.user_id, "chat_message", {
                "workspace_id": payload.workspaceId,
                "query_length": len(payload.query or ""),
            })
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
            else:
                if not payload.target:
                    raise HTTPException(
                        status_code=400,
                        detail="target is required for file test generation",
                    )
            _apply_rate_headers(response, rate_limit_guard.enforce(principal, "ai_generation"))
            if payload.generationMode == "scenario":
                telemetry.capture(principal.user_id, "scenario_generation", {
                    "workspace_id": payload.workspaceId,
                    "test_type": test_type,
                })
                prompt, markdown = ai_service.generate_tests_from_scenario(
                    repository_metadata, payload.scenario.strip(), test_type,
                )
            else:
                prompt, markdown = ai_service.generate_tests(
                    repository_metadata, payload.target, test_type,
                )
                telemetry.capture(principal.user_id, "test_generation", {
                    "workspace_id": payload.workspaceId,
                    "target": payload.target or "",
                    "test_type": test_type,
                })

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

    except (HTTPException, QuotaAPIError):
        raise
    except AIProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI query failed: {str(exc)}") from exc


@app.post("/ai/generate-tests", response_model=GenerateTestsResponse, deprecated=True)
def generate_tests(payload: GenerateTestsRequest, response: Response, principal: Principal = Depends(auth.active_principal)):
    """Deprecated — use POST /ai/query with type=test_generation instead."""
    try:
        _, repository_metadata = _load_workspace(payload.workspaceId, principal)
        _apply_rate_headers(response, rate_limit_guard.enforce(principal, "ai_generation"))
        prompt, markdown = ai_service.generate_tests(repository_metadata, payload.target, payload.type)

        return GenerateTestsResponse(
            workspaceId=payload.workspaceId,
            target=payload.target,
            type=payload.type,
            prompt=prompt,
            markdown=markdown,
        )
    except (HTTPException, QuotaAPIError):
        raise
    except AIProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate tests: {str(exc)}") from exc


@app.post("/workspaces/impact-analysis", response_model=ImpactAnalysisResult)
def impact_analysis(payload: ImpactAnalysisRequest, principal: Principal = Depends(auth.active_principal)):
    try:
        _, repository_metadata = _load_workspace(payload.workspaceId, principal)
        return impact_analysis_service.analyze(repository_metadata, payload.target)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Impact analysis failed: {str(exc)}") from exc


@app.delete("/admin/rate-limits/{user_id}")
def clear_user_rate_limits(
    user_id: str,
    principal: Principal = Depends(auth.admin_principal),
):
    del principal
    try:
        result = rate_limit_service.clear_user(user_id)
        return {
            "userId": user_id,
            "requestKeysRemoved": result.request_keys_removed,
            "concurrencyEntriesRemoved": result.concurrency_entries_removed,
        }
    except RateLimitBackendUnavailable as exc:
        raise QuotaAPIError(
            503, "RATE_LIMIT_UNAVAILABLE", "The quota service is temporarily unavailable.",
            {}, {"Retry-After": "30"},
        ) from exc


@app.get("/admin/feature-flags", response_model=list[FeatureFlagRecord])
def list_feature_flags(principal: Principal = Depends(auth.admin_principal)):
    del principal
    return feature_flag_service.list_flags()


@app.put("/admin/feature-flags/{key}", response_model=FeatureFlagRecord)
def update_feature_flag(
    key: str,
    payload: FeatureFlagUpdateRequest,
    principal: Principal = Depends(auth.admin_principal),
):
    try:
        return feature_flag_service.update(key, payload.enabled, principal.user_id)
    except FeatureFlagNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Feature flag '{key}' was not found.") from exc
