from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
from app.models.code_models import RepositoryMetadata
from app.services.repository_services import RepositoryService
from app.services.parser_services import ParserService
from app.services.repository_indexer_service import RepositoryIndexerService

app = FastAPI(title="TestForge AI")
repo_service = RepositoryService()
parser_service = ParserService()
repository_indexer = RepositoryIndexerService(repo_service, parser_service)

# Workspace base directory path relative to this main.py file
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_DIR = os.path.join(BASE_DIR, "workspace/repositories")

# Ensure workspace folder exists
os.makedirs(WORKSPACE_DIR, exist_ok=True)

class IndexRequest(BaseModel):
    githubUrl: str

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
