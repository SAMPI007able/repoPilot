from pydantic import BaseModel, Field, model_validator


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
    branch: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        pattern=r"^[A-Za-z0-9_][A-Za-z0-9._/-]*$",
    )
    project_docs: list[str] = Field(default_factory=list, alias="projectDocs")

    @model_validator(mode="after")
    def validate_branch(self):
        if self.branch and (
            ".." in self.branch
            or "@{" in self.branch
            or self.branch.endswith((".", "/"))
        ):
            raise ValueError("branch is not a safe Git branch name")
        return self


class ReindexWorkspaceRequest(BaseModel):
    branch: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        pattern=r"^[A-Za-z0-9_][A-Za-z0-9._/-]*$",
    )

    @model_validator(mode="after")
    def validate_branch(self):
        if self.branch and (
            ".." in self.branch
            or "@{" in self.branch
            or self.branch.endswith((".", "/"))
        ):
            raise ValueError("branch is not a safe Git branch name")
        return self
