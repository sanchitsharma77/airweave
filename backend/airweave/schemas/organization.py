"""Organization schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from airweave.core.shared_models import FeatureFlag as FeatureFlagEnum


class OrganizationBase(BaseModel):
    """Organization base schema."""

    name: str = Field(..., min_length=4, max_length=100, description="Organization name")
    description: Optional[str] = Field(None, max_length=500, description="Organization description")
    auth0_org_id: Optional[str] = Field(None, description="Auth0 organization ID")


class OrganizationCreate(OrganizationBase):
    """Organization creation schema."""

    org_metadata: Optional[Dict[str, Any]] = Field(
        None, description="Additional organization metadata"
    )


class OrganizationUpdate(BaseModel):
    """Organization update schema."""

    name: str
    description: Optional[str] = None
    org_metadata: Optional[Dict[str, Any]] = None


class OrganizationInDBBase(OrganizationBase):
    """Organization base schema in the database."""

    model_config = {"from_attributes": True}

    id: UUID
    created_at: datetime
    modified_at: datetime
    org_metadata: Optional[Dict[str, Any]] = None


class Organization(OrganizationInDBBase):
    """Organization schema."""

    name: str
    description: Optional[str] = None
    auth0_org_id: Optional[str] = None
    enabled_features: List[FeatureFlagEnum] = Field(
        default_factory=list,
        description="List of enabled feature flags for this organization",
    )


class OrganizationWithRole(BaseModel):
    """Organization schema with user's role information."""

    model_config = {"from_attributes": True}

    id: UUID
    name: str
    description: Optional[str] = None
    created_at: datetime
    modified_at: datetime
    role: str  # owner, admin, member
    is_primary: bool
    auth0_org_id: Optional[str] = None
    org_metadata: Optional[Dict[str, Any]] = None
    enabled_features: List[FeatureFlagEnum] = Field(
        default_factory=list,
        description="List of enabled feature flags for this organization",
    )
