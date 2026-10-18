from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TestGenerationSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    workspace_id: str = Field(alias="workspaceId")
    mode: str
    test_type: str = Field(alias="testType")
    target: str | None
    scenario: str | None
    cache_hit: bool = Field(alias="cacheHit")
    created_at: datetime = Field(alias="createdAt")


class TestGenerationRecord(TestGenerationSummary):
    markdown: str
