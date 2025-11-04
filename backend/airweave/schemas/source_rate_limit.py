"""Source rate limit schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SourceRateLimitBase(BaseModel):
    """Base schema for source rate limits.

    Stores ONE limit per (organization, source). The limit applies to all
    users/connections of that source in the organization.
    """

    source_short_name: str = Field(
        ..., description="Source identifier (e.g., 'google_drive', 'notion')"
    )
    limit: int = Field(..., gt=0, description="Maximum requests allowed per window")
    window_seconds: int = Field(
        default=60, gt=0, description="Time window in seconds (60=per minute, 86400=per day, etc.)"
    )


class SourceRateLimitCreate(SourceRateLimitBase):
    """Schema for creating a new source rate limit."""

    pass


class SourceRateLimitUpdate(BaseModel):
    """Schema for updating source rate limit."""

    limit: Optional[int] = Field(None, gt=0, description="Updated request limit")
    window_seconds: Optional[int] = Field(None, gt=0, description="Updated time window in seconds")


class SourceRateLimit(SourceRateLimitBase):
    """Complete source rate limit schema."""

    id: UUID
    organization_id: UUID
    source_short_name: str  # Inherited from Base, but explicit for clarity
    limit: int  # Inherited from Base
    window_seconds: int  # Inherited from Base
    created_at: datetime
    modified_at: datetime

    class Config:
        """Pydantic config."""

        from_attributes = True
