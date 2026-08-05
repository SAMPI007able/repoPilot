from pydantic import BaseModel, Field


class ProviderConnection(BaseModel):
    provider: str
    name: str
    configured: bool
    connected: bool
    account_name: str | None = Field(default=None, alias="accountName")
    avatar_url: str | None = Field(default=None, alias="avatarUrl")


class OAuthConnectResponse(BaseModel):
    authorization_url: str = Field(alias="authorizationUrl")


class ProviderRepository(BaseModel):
    id: str
    provider: str
    owner: str
    name: str
    full_name: str = Field(alias="fullName")
    description: str | None = None
    private: bool
    default_branch: str = Field(alias="defaultBranch")
    web_url: str = Field(alias="webUrl")
    clone_url: str = Field(alias="cloneUrl")
    updated_at: str | None = Field(default=None, alias="updatedAt")
    stars: int = 0


class RepositoryContent(BaseModel):
    path: str
    content: str
    encoding: str = "utf-8"


class ImportRepositoryRequest(BaseModel):
    owner: str
    repo: str
    project_docs: list[str] = Field(default_factory=list, alias="projectDocs")
