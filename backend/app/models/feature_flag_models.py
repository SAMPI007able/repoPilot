from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FeatureFlagsResponse(BaseModel):
    flags: dict[str, bool]


class FeatureFlagRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    key: str
    enabled: bool
    description: str | None = None
    updated_at: datetime = Field(alias="updatedAt")
    updated_by_user_id: str | None = Field(alias="updatedByUserId")


class FeatureFlagUpdateRequest(BaseModel):
    enabled: bool
