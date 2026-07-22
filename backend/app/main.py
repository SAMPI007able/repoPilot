from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Body
from pydantic import BaseModel
from typing import Literal, Optional
import os

from app.models.code_models import DocumentationAsset, ImpactAnalysisResult, RepositoryMetadata
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
WORKSPACE_DIR = os.path.join(BASE_DIR, "workspace/repositories")
os.makedirs(WORKSPACE_DIR, exist_ok=True)


# ── Request / Response models ────────────────────────────────────────────────
class IndexRequest(BaseModel):
    githubUrl: str


def _save_project_documents(
    workspace_path: str,
    project_docs: list[UploadFile] | None,
) -> list[DocumentationAsset]:
    if not project_docs:
        return []

    documentation_dir = os.path.join(workspace_path, 'project_docs')
    os.makedirs(documentation_dir, exist_ok=True)

    assets: list[DocumentationAsset] = []
    for upload in project_docs:
        filename = os.path.basename(upload.filename)
        target_path = os.path.join(documentation_dir, filename)
        contents = upload.file.read()

        with open(target_path, 'wb') as saved_file:
            saved_file.write(contents)

        ext = os.path.splitext(filename)[1].lower()
        if ext in {'.md', '.txt', '.json', '.yaml', '.yml', '.rst', '.xml', '.csv'}:
            source = contents.decode('utf-8', errors='ignore')
        elif ext == '.pdf':
            source = f"[Uploaded PDF document '{filename}' saved to project_docs. Text extraction is not yet supported.]"
        elif ext in {'.docx', '.pptx'}:
            source = f"[Uploaded document '{filename}' saved to project_docs. Text extraction is not yet supported.]"
        else:
            source = contents.decode('utf-8', errors='ignore')

        assets.append(
            DocumentationAsset(
                path=os.path.relpath(target_path, workspace_path).replace('\\', '/'),
                source=source,
            )
        )

    return assets


class QueryRequest(BaseModel):
    """
    Unified AI query request.

    type = "chat"
        • query  — the free-form codebase question
        • workspaceId — the indexed repository to query against

    type = "test_generation"
        • workspaceId — the indexed repository
        • target      — file name or class name to generate tests for
        • testType    — e.g. "unit", "integration", "e2e"
    """
    type: Literal["chat", "test_generation"]
    workspaceId: str
    query: Optional[str] = None      # used by chat
    target: Optional[str] = None     # used by test_generation
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
    workspace_path = os.path.join(WORKSPACE_DIR, workspace_id)
    if not os.path.isdir(workspace_path):
        raise HTTPException(
            status_code=404,
            detail=f"Workspace '{workspace_id}' not found. Index it first via POST /workspaces/index.",
        )
    metadata = repository_indexer.index_repository(workspace_id, workspace_path)
    return workspace_path, metadata


# ── Routes ───────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/workspaces/index", response_model=RepositoryMetadata)
def index_workspace(
    githubUrl: str | None = Form(None),
    project_docs: list[UploadFile] | None = File(default=None),
    payload: IndexRequest | None = Body(None),
):
    git_url = githubUrl or (payload.githubUrl if payload else None)
    if not git_url:
        raise HTTPException(status_code=400, detail="githubUrl is required")

    try:
        repo_name = repo_service.extract_repo_name(git_url)
        destination_path = os.path.join(WORKSPACE_DIR, repo_name)
        repo_service.clone_repository(git_url, destination_path)
        uploaded_docs = _save_project_documents(destination_path, project_docs)
        return repository_indexer.index_repository(repo_name, destination_path, uploaded_docs=uploaded_docs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to index workspace: {str(e)}")


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
            if not payload.target:
                raise HTTPException(status_code=400, detail="target is required for type=test_generation")

            test_type = payload.testType or "unit"
            prompt, markdown = ai_service.generate_tests(repository_metadata, payload.target, test_type)

            return QueryResponse(
                type="test_generation",
                workspaceId=payload.workspaceId,
                prompt=prompt,
                markdown=markdown,
                target=payload.target,
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
