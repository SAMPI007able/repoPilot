from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic.alias_generators import to_camel


EnvironmentName = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{0,127}$")]


class ManifestModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class RuntimeConfiguration(ManifestModel):
    family: Literal["node"] = "node"
    version: Literal["20", "22"] = "22"


class RepositoryConfiguration(ManifestModel):
    branch: str = Field(
        default="main",
        min_length=1,
        max_length=255,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$",
    )

    @model_validator(mode="after")
    def validate_branch(self):
        if ".." in self.branch or "@{" in self.branch or self.branch.endswith((".", "/")):
            raise ValueError("repository.branch is not a safe Git branch name")
        return self


class CommandConfiguration(ManifestModel):
    command: str = Field(min_length=1, max_length=240)


class HealthcheckConfiguration(ManifestModel):
    path: str = Field(default="/", pattern=r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/\-]*$")
    timeout_seconds: int = Field(default=180, ge=10, le=600)
    interval_seconds: int = Field(default=3, ge=1, le=30)


class RuntimeServiceConfiguration(ManifestModel):
    name: str = Field(default="web", pattern=r"^[a-z][a-z0-9-]{0,31}$")
    command: str = Field(min_length=1, max_length=240)
    port: int = Field(ge=1024, le=65535)
    public: bool = True
    healthcheck: HealthcheckConfiguration = Field(default_factory=HealthcheckConfiguration)


class EnvironmentConfiguration(ManifestModel):
    required: list[EnvironmentName] = Field(default_factory=list, max_length=100)
    optional: list[EnvironmentName] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_names(self):
        self.required = list(dict.fromkeys(self.required))
        self.optional = list(dict.fromkeys(self.optional))
        overlap = set(self.required).intersection(self.optional)
        if overlap:
            raise ValueError(
                f"Environment variables cannot be both required and optional: {', '.join(sorted(overlap))}"
            )
        return self


class ResourceConfiguration(ManifestModel):
    cpu_request: str = "250m"
    cpu_limit: str = "1"
    memory_request: str = "256Mi"
    memory_limit: str = "1Gi"


class LifecycleConfiguration(ManifestModel):
    idle_timeout_minutes: int = Field(default=20, ge=5, le=60)
    maximum_lifetime_minutes: int = Field(default=60, ge=10, le=240)

    @model_validator(mode="after")
    def validate_timeouts(self):
        if self.idle_timeout_minutes > self.maximum_lifetime_minutes:
            raise ValueError("idleTimeoutMinutes cannot exceed maximumLifetimeMinutes")
        return self


class RuntimeManifest(ManifestModel):
    version: Literal["1"] = "1"
    runtime: RuntimeConfiguration
    repository: RepositoryConfiguration
    install: CommandConfiguration
    build: CommandConfiguration
    services: list[RuntimeServiceConfiguration] = Field(min_length=1, max_length=3)
    environment: EnvironmentConfiguration = Field(default_factory=EnvironmentConfiguration)
    resources: ResourceConfiguration = Field(default_factory=ResourceConfiguration)
    lifecycle: LifecycleConfiguration = Field(default_factory=LifecycleConfiguration)


class AnalysisEvidence(ManifestModel):
    field: str
    source: str
    detail: str
    confidence: float = Field(ge=0, le=1)


class RuntimeAnalysisSummary(ManifestModel):
    framework: str
    package_manager: Literal["npm", "pnpm", "yarn"]
    confidence: float = Field(ge=0, le=1)


class RuntimeManifestAnalysis(ManifestModel):
    manifest: RuntimeManifest
    summary: RuntimeAnalysisSummary
    evidence: list[AnalysisEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    supported: bool = True
    unsupported_reasons: list[str] = Field(default_factory=list)


class RuntimeManifestRecord(RuntimeManifestAnalysis):
    workspace_id: str
    approved: bool = False
    revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None = None


class RuntimeManifestAnalyzeRequest(ManifestModel):
    instructions: str | None = Field(default=None, max_length=4000)


class RuntimeManifestUpdateRequest(ManifestModel):
    manifest: RuntimeManifest
    expected_revision: int = Field(ge=1)


class RuntimeManifestApproveRequest(ManifestModel):
    expected_revision: int = Field(ge=1)


class PreviewErrorEnvelope(ManifestModel):
    code: str
    message: str
    retryable: bool = False
    details: dict = Field(default_factory=dict)
    correlation_id: str
