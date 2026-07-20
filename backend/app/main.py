from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
from app.models.code_models import RepositoryMetadata
from app.services.ai.ai_service import AIService
from app.services.ai.gemini_provider import GeminiProvider
from app.services.context_builder_service import ContextBuilderService
from app.services.graph_services import GraphService
from app.services.prompt_builder_service import PromptBuilderService
from app.services.repository_services import RepositoryService
from app.services.parser_services import ParserService
from app.services.repository_indexer_service import RepositoryIndexerService

from fastapi.middleware.cors import CORSMiddleware
    
app = FastAPI(title="TestForge AI")
origins = [
    "http://localhost:5173",   
    "http://127.0.0.1:5173" 
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,          # list of allowed origins
    allow_credentials=True,
    allow_methods=["*"],            # allow all HTTP methods
    allow_headers=["*"],            # allow all headers
)
repo_service = RepositoryService()
parser_service = ParserService()
graph_service = GraphService()
repository_indexer = RepositoryIndexerService(repo_service, parser_service, graph_service)
context_builder_service = ContextBuilderService(graph_service)
prompt_builder_service = PromptBuilderService()
ai_service = AIService(GeminiProvider())

# Workspace base directory path relative to this main.py file
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_DIR = os.path.join(BASE_DIR, "workspace/repositories")

# Ensure workspace folder exists
os.makedirs(WORKSPACE_DIR, exist_ok=True)

class IndexRequest(BaseModel):
    githubUrl: str


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


@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/workspaces/index", response_model=RepositoryMetadata)
def index_workspace(payload: IndexRequest):
    git_url = payload.githubUrl
    if not git_url:
        raise HTTPException(status_code=400, detail="githubUrl is required")

    try:
        repo_name = repo_service.extract_repo_name(git_url)
        destination_path = os.path.join(WORKSPACE_DIR, repo_name)
        
        # Clone the repository
        repo_service.clone_repository(git_url, destination_path)

        return repository_indexer.index_repository(repo_name, destination_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to index workspace: {str(e)}")


@app.post("/ai/generate-tests", response_model=GenerateTestsResponse)
def generate_tests(payload: GenerateTestsRequest):
    workspace_id = payload.workspaceId
    if not workspace_id:
        raise HTTPException(status_code=400, detail="workspaceId is required")
    if not payload.target:
        raise HTTPException(status_code=400, detail="target is required")
    if not payload.type:
        raise HTTPException(status_code=400, detail="type is required")

    workspace_path = os.path.join(WORKSPACE_DIR, workspace_id)
    if not os.path.isdir(workspace_path):
        raise HTTPException(
            status_code=404,
            detail=f"Workspace '{workspace_id}' was not found at {workspace_path}",
        )

    try:
        repository_metadata = repository_indexer.index_repository(workspace_id, workspace_path)
        context = context_builder_service.build_context(
            repository_metadata=repository_metadata,
            target=payload.target,
            test_type=payload.type,
        )
        prompt = prompt_builder_service.build_prompt(context)
        markdown = ai_service.generate_tests(prompt)

        return GenerateTestsResponse(
            workspaceId=workspace_id,
            target=payload.target,
            type=payload.type,
            prompt=prompt,
            markdown=markdown,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate tests: {str(exc)}") from exc
