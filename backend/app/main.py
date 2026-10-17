from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Body, Request, Header, Depends, Response, BackgroundTasks
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
import urllib.parse

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
from app.models.admin_models import (
    AdminBrowserSession, AdminDashboard, AdminLog, AdminPreview, AdminUsage,
    AdminUser, AdminUserStatusUpdate,
)
from app.models.integration_models import (
    ImportRepositoryRequest, OAuthConnectResponse, ProviderConnection,
    ProviderRepository, RepositoryContent, ReindexWorkspaceRequest,
)
from app.persistence.identity_persistence_service import IdentityPersistenceService
from app.persistence.chat_persistence_service import ChatPersistenceService, ChatSessionNotFoundError
from app.models.chat_models import ChatSession
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
from app.services.admin_service import AdminConflictError, AdminResourceNotFoundError, AdminService
from app.models.support_models import (
    AdminSupportTicket, SupportTicket, SupportTicketCreateRequest, SupportTicketStatus,
    SupportTicketStatusUpdate, SupportUploadResponse,
)
from app.persistence.support_persistence_service import (
    SupportAttachmentNotFoundError, SupportPersistenceService, SupportTicketNotFoundError,
    SupportTicketTransitionError,
)
from app.services.email_service import EmailService, EmailSettings
from app.services.support_service import MAX_ATTACHMENT_BYTES, SupportService, SupportValidationError

from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

app = FastAPI(title="RepoPilot")
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
    try:
        admin_service.record_log("authentication", exc.message, code=exc.code)
    except Exception:
        pass
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
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)

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
chat_ai_provider = GeminiProvider(
    thinking_level=os.getenv("GEMINI_CHAT_THINKING_LEVEL", "minimal")
)
generation_ai_provider = GeminiProvider(
    thinking_level=os.getenv("GEMINI_GENERATION_THINKING_LEVEL", "low")
)
chat_capability = ChatCapability(chat_ai_provider, chat_prompt_builder_service)
test_generation_capability = TestGenerationCapability(
    generation_ai_provider, context_builder_service, prompt_builder_service
)
documentation_capability = DocumentationCapability(
    generation_ai_provider, documentation_prompt_builder_service
)
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
chat_persistence_service = ChatPersistenceService(database)
admin_service = AdminService(database)
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
            StructuredAIRuntimeManifestFallback(generation_ai_provider)
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
support_service = SupportService(
    SupportPersistenceService(database),
    artifact_store,
    EmailService(EmailSettings.from_env()),
    failure_logger=lambda message, _ticket_id: admin_service.record_log(
        "support_email", message, code="SUPPORT_EMAIL_FAILED",
    ),
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
    sessionId: Optional[str] = None  # scopes follow-up context for chat
    target: Optional[str] = None     # used by test_generation
    scenario: Optional[str] = None   # used by scenario-based test_generation
    generationMode: Literal["file", "scenario"] = "file"
    testType: Optional[str] = None   # used by test_generation


class QueryResponse(BaseModel):
    type: str
    workspaceId: str
    prompt: str
    markdown: str
    sessionId: Optional[str] = None
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


def _repository_clone_token(repository_url: str, principal: Principal) -> str | None:
    hostname = (urllib.parse.urlsplit(repository_url).hostname or "").lower()
    provider_by_hostname = {
        "github.com": "github",
        "www.github.com": "github",
        "gitlab.com": "gitlab",
        "bitbucket.org": "bitbucket",
    }
    provider = provider_by_hostname.get(hostname)
    if not provider:
        return None
    connection = next(
        (item for item in oauth_integration_service.statuses(principal.user_id) if item.provider == provider),
        None,
    )
    if not connection or not connection.connected:
        return None
    return oauth_integration_service.access_token(principal.user_id, provider)


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


@app.get("/integrations/{provider}/branches", response_model=list[str])
def list_integration_repository_branches(
    provider: str,
    owner: str,
    repo: str,
    principal: Principal = Depends(auth.active_principal),
):
    try:
        return oauth_integration_service.branches(
            principal.user_id, provider, owner, repo
        )
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
        if payload.branch:
            branches = oauth_integration_service.branches(
                principal.user_id, provider, payload.owner, payload.repo
            )
            if payload.branch not in branches:
                raise HTTPException(
                    status_code=400,
                    detail=f"Branch '{payload.branch}' is not available in this repository.",
                )
        _apply_rate_headers(response, rate_limit_guard.enforce(principal, "repository_index"))
        telemetry.capture(principal.user_id, "repo_connected", {
            "source": "integration_import",
            "provider": provider,
            "repository_url": repository.clone_url,
            "repository_owner": payload.owner,
            "repository_name": payload.repo,
        })
        selected_branch = payload.branch or repository.default_branch
        workspace = workspace_build_service.start_build(
            repository.clone_url, owner_user_id=principal.user_id,
            clone_authorization=token, trusted_provider_url=True,
            branch=selected_branch,
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
            _require_feature("uploads")
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


@app.get("/workspaces/{workspace_id}/branches", response_model=list[str])
def list_workspace_branches(
    workspace_id: str,
    principal: Principal = Depends(auth.active_principal),
):
    _authorize_workspace(workspace_id, principal)
    workspace = workspace_build_service.get_workspace_summary(workspace_id, principal.user_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"Workspace '{workspace_id}' was not found.")
    try:
        return workspace_build_service.list_branches(
            workspace_id,
            principal.user_id,
            _repository_clone_token(workspace.repoUrl, principal),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to load repository branches: {exc}") from exc


@app.post(
    "/workspaces/{workspace_id}/reindex",
    response_model=WorkspaceBuildJob,
    status_code=202,
)
def reindex_workspace(
    workspace_id: str,
    payload: ReindexWorkspaceRequest,
    response: Response,
    principal: Principal = Depends(auth.active_principal),
):
    _authorize_workspace(workspace_id, principal)
    workspace = workspace_build_service.get_workspace_summary(workspace_id, principal.user_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"Workspace '{workspace_id}' was not found.")
    try:
        token = _repository_clone_token(workspace.repoUrl, principal)
        if payload.branch:
            branches = workspace_build_service.list_branches(
                workspace_id, principal.user_id, token
            )
            if payload.branch not in branches:
                raise HTTPException(
                    status_code=400,
                    detail=f"Branch '{payload.branch}' is not available in this repository.",
                )
        _apply_rate_headers(response, rate_limit_guard.enforce(principal, "repository_index"))
        job = workspace_build_service.start_reindex(
            workspace_id,
            principal.user_id,
            branch=payload.branch,
            clone_authorization=token,
        )
        telemetry.capture(principal.user_id, "repo_reindexed", {
            "workspace_id": workspace_id,
            "repository_url": workspace.repoUrl,
            "branch": payload.branch or workspace.indexedBranch,
        })
        return job
    except HTTPException:
        raise
    except WorkspaceBuildAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to start re-index: {exc}") from exc


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


@app.post("/workspaces/{workspace_id}/chat-sessions", response_model=ChatSession, status_code=201)
def create_chat_session(
    workspace_id: str,
    principal: Principal = Depends(auth.active_principal),
):
    _authorize_workspace(workspace_id, principal)
    return chat_persistence_service.create(principal.user_id, workspace_id)


@app.get("/workspaces/{workspace_id}/chat-sessions/latest", response_model=ChatSession)
def latest_chat_session(
    workspace_id: str,
    principal: Principal = Depends(auth.active_principal),
):
    _authorize_workspace(workspace_id, principal)
    session = chat_persistence_service.latest(principal.user_id, workspace_id)
    if session is None:
        raise HTTPException(status_code=404, detail="No chat session exists for this workspace.")
    return session


@app.post("/ai/query/stream")
def stream_ai_query(
    payload: QueryRequest,
    principal: Principal = Depends(auth.active_principal),
):
    """Stream chat responses as newline-delimited JSON events."""
    if payload.type != "chat":
        raise HTTPException(status_code=400, detail="Streaming is only supported for chat queries.")
    if not payload.query:
        raise HTTPException(status_code=400, detail="query is required for type=chat")

    _require_feature("ai_generation")
    _, repository_metadata = _load_workspace(payload.workspaceId, principal)
    rate_decision = rate_limit_guard.enforce(principal, "project_chat")

    if payload.sessionId:
        chat_session = chat_persistence_service.get(
            payload.sessionId, principal.user_id, payload.workspaceId,
        )
    else:
        chat_session = chat_persistence_service.create(principal.user_id, payload.workspaceId)
    history = chat_persistence_service.context(
        chat_session.id, principal.user_id, payload.workspaceId,
    )
    _, chunks = ai_service.stream_chat(repository_metadata, payload.query, history)

    def event(payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"

    def stream_events():
        yield event({"type": "metadata", "sessionId": chat_session.id})
        answer_parts: list[str] = []
        try:
            for chunk in chunks:
                answer_parts.append(chunk)
                yield event({"type": "delta", "text": chunk})

            markdown = "".join(answer_parts)
            if not markdown:
                raise RuntimeError("The AI provider returned an empty response.")
            chat_persistence_service.append_exchange(
                chat_session.id,
                principal.user_id,
                payload.workspaceId,
                payload.query,
                markdown,
            )
            admin_service.record_usage(principal.user_id, "ai_request")
            telemetry.capture(principal.user_id, "chat_message", {
                "workspace_id": payload.workspaceId,
                "query_length": len(payload.query),
                "streamed": True,
            })
            yield event({"type": "done", "sessionId": chat_session.id})
        except AIProviderUnavailableError as exc:
            try:
                admin_service.record_log(
                    "runtime", str(exc), code="AI_PROVIDER_UNAVAILABLE", user_id=principal.user_id,
                )
            except Exception:
                pass
            yield event({"type": "error", "message": str(exc)})
        except Exception:
            try:
                admin_service.record_log(
                    "runtime",
                    "The streamed AI query failed.",
                    code="AI_STREAM_FAILED",
                    user_id=principal.user_id,
                )
            except Exception:
                pass
            yield event({
                "type": "error",
                "message": "The AI response was interrupted. Please try again.",
            })

    headers = {
        **rate_decision.headers,
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        stream_events(),
        media_type="application/x-ndjson",
        headers=headers,
    )


@app.post("/ai/query", response_model=QueryResponse)
def ai_query(payload: QueryRequest, response: Response, principal: Principal = Depends(auth.active_principal)):
    """
    Unified AI query endpoint.

    Supported types:
    - "chat"             → free-form codebase question
    - "test_generation"  → generate tests for a target file/class
    """
    try:
        _require_feature("ai_generation")
        _, repository_metadata = _load_workspace(payload.workspaceId, principal)

        if payload.type == "chat":
            if not payload.query:
                raise HTTPException(status_code=400, detail="query is required for type=chat")

            _apply_rate_headers(response, rate_limit_guard.enforce(principal, "project_chat"))
            if payload.sessionId:
                chat_session = chat_persistence_service.get(
                    payload.sessionId, principal.user_id, payload.workspaceId,
                )
            else:
                chat_session = chat_persistence_service.create(principal.user_id, payload.workspaceId)
            history = chat_persistence_service.context(
                chat_session.id, principal.user_id, payload.workspaceId,
            )
            prompt, markdown = ai_service.chat(repository_metadata, payload.query, history)
            chat_persistence_service.append_exchange(
                chat_session.id, principal.user_id, payload.workspaceId, payload.query, markdown,
            )
            admin_service.record_usage(principal.user_id, "ai_request")
            telemetry.capture(principal.user_id, "chat_message", {
                "workspace_id": payload.workspaceId,
                "query_length": len(payload.query or ""),
            })
            return QueryResponse(
                type="chat",
                workspaceId=payload.workspaceId,
                prompt=prompt,
                markdown=markdown,
                sessionId=chat_session.id,
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

            admin_service.record_usage(principal.user_id, "ai_request")

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

    except ChatSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Chat session not found in this workspace.") from exc
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
        _require_feature("ai_generation")
        _, repository_metadata = _load_workspace(payload.workspaceId, principal)
        _apply_rate_headers(response, rate_limit_guard.enforce(principal, "ai_generation"))
        prompt, markdown = ai_service.generate_tests(repository_metadata, payload.target, payload.type)
        admin_service.record_usage(principal.user_id, "ai_request")

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


@app.post("/support/tickets", response_model=SupportTicket, status_code=201)
def create_support_ticket(
    payload: SupportTicketCreateRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    principal: Principal = Depends(auth.active_principal),
):
    _apply_rate_headers(response, rate_limit_guard.enforce(principal, "support_ticket"))
    try:
        ticket = support_service.create_ticket(principal.user_id, payload)
    except SupportValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    background_tasks.add_task(support_service.notify_admins_of_new_ticket, ticket)
    telemetry.capture(principal.user_id, "support_ticket_created", {"category": ticket.category.value})
    return SupportTicket(**ticket.model_dump(by_alias=True))


@app.get("/support/tickets", response_model=list[SupportTicket])
def list_my_support_tickets(principal: Principal = Depends(auth.active_principal)):
    return support_service.list_for_user(principal.user_id)


@app.post("/support/uploads", response_model=SupportUploadResponse, status_code=201)
def upload_support_image(
    request: Request,
    response: Response,
    upload: UploadFile = File(...),
    principal: Principal = Depends(auth.active_principal),
):
    _require_feature("uploads")
    _apply_rate_headers(response, rate_limit_guard.enforce(principal, "document_upload"))
    contents = upload.file.read(MAX_ATTACHMENT_BYTES + 1)
    try:
        url = support_service.store_image(principal.user_id, contents, str(request.base_url))
    except SupportValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SupportUploadResponse(url=url)


@app.get("/support/uploads/{attachment_id}")
def get_support_image(attachment_id: str):
    # Attachment ids are unguessable UUIDs so images render in <img> tags and admin emails without auth headers.
    try:
        uuid.UUID(attachment_id)
        contents, content_type = support_service.load_image(attachment_id)
    except (ValueError, SupportAttachmentNotFoundError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Attachment not found.") from exc
    return Response(
        content=contents,
        media_type=content_type,
        headers={
            "Cache-Control": "private, max-age=86400",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@app.get("/admin/support/tickets", response_model=list[AdminSupportTicket])
def admin_support_tickets(
    status: SupportTicketStatus | None = None,
    principal: Principal = Depends(auth.admin_principal),
):
    del principal
    return support_service.list_all(status)


@app.put("/admin/support/tickets/{ticket_id}/status", response_model=AdminSupportTicket)
def admin_update_support_ticket_status(
    ticket_id: str,
    payload: SupportTicketStatusUpdate,
    background_tasks: BackgroundTasks,
    principal: Principal = Depends(auth.admin_principal),
):
    try:
        ticket = support_service.update_status(ticket_id, payload.status, principal.user_id)
    except SupportTicketNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Support ticket not found.") from exc
    except SupportTicketTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(support_service.notify_requester_of_status, ticket)
    return ticket


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


@app.get("/admin/dashboard", response_model=AdminDashboard)
def admin_dashboard(principal: Principal = Depends(auth.admin_principal)):
    del principal
    return admin_service.dashboard()


@app.get("/admin/users", response_model=list[AdminUser])
def admin_users(q: str = "", principal: Principal = Depends(auth.admin_principal)):
    del principal
    return admin_service.users(q)


@app.put("/admin/users/{user_id}/status", response_model=AdminUser)
def admin_update_user_status(
    user_id: str,
    payload: AdminUserStatusUpdate,
    principal: Principal = Depends(auth.admin_principal),
):
    try:
        return admin_service.set_suspended(user_id, payload.suspended, principal.user_id)
    except AdminResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="User not found.") from exc
    except AdminConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/admin/users/{user_id}", status_code=204)
def admin_delete_user(user_id: str, principal: Principal = Depends(auth.admin_principal)):
    try:
        admin_service.delete_user(user_id, principal.user_id)
    except AdminResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="User not found.") from exc
    except AdminConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/admin/previews", response_model=list[AdminPreview])
def admin_previews(principal: Principal = Depends(auth.admin_principal)):
    del principal
    return admin_service.active_previews()


@app.post("/admin/previews/{preview_id}/terminate", response_model=PreviewEnvironment, status_code=202)
def admin_terminate_preview(preview_id: str, principal: Principal = Depends(auth.admin_principal)):
    del principal
    try:
        preview = preview_service.stop(preview_id)
        owner_user_id = preview_persistence_service.owner_user_id(preview_id)
        if owner_user_id:
            rate_limit_service.release_concurrency_slot(owner_user_id, "preview", preview_id)
        return preview
    except Exception as exc:
        _raise_preview_error(exc)


@app.get("/admin/browser-sessions", response_model=list[AdminBrowserSession])
def admin_browser_sessions(principal: Principal = Depends(auth.admin_principal)):
    del principal
    return admin_service.active_browser_sessions()


@app.post("/admin/browser-sessions/{session_id}/terminate", status_code=204)
def admin_terminate_browser_session(session_id: str, principal: Principal = Depends(auth.admin_principal)):
    del principal
    try:
        admin_service.terminate_browser_session(session_id)
    except AdminResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Browser session not found.") from exc


@app.get("/admin/usage", response_model=list[AdminUsage])
def admin_usage(principal: Principal = Depends(auth.admin_principal)):
    del principal
    return admin_service.usage()


@app.get("/admin/logs", response_model=list[AdminLog])
def admin_logs(principal: Principal = Depends(auth.admin_principal)):
    del principal
    return admin_service.logs()


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
