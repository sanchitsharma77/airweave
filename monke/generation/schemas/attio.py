"""Attio-specific Pydantic schemas used for LLM structured generation."""

from typing import List
from pydantic import BaseModel, Field


class AttioCompanySpec(BaseModel):
    """Metadata for company generation."""

    name: str = Field(description="Company name")
    token: str = Field(description="Unique verification token to embed in the content")
    domain: str = Field(description="Company domain (e.g., acme.com)")
    industry: str = Field(description="Industry/sector")


class AttioCompanyContent(BaseModel):
    """Content for generated company record."""

    description: str = Field(description="Company description with embedded token")
    categories: List[str] = Field(description="Categories/tags for the company")
    key_products: List[str] = Field(description="Key products or services")
    notes: str = Field(description="Additional notes about the company")


class AttioCompany(BaseModel):
    """Schema for generating Attio company content."""

    spec: AttioCompanySpec
    content: AttioCompanyContent


class AttioPersonSpec(BaseModel):
    """Metadata for person generation."""

    first_name: str = Field(description="First name")
    last_name: str = Field(description="Last name")
    token: str = Field(description="Unique verification token")
    email: str = Field(description="Email address")
    title: str = Field(description="Job title")


class AttioPersonContent(BaseModel):
    """Content for generated person record."""

    bio: str = Field(description="Person bio with embedded token")
    interests: List[str] = Field(description="Professional interests")
    notes: str = Field(description="Additional notes about the person")


class AttioPerson(BaseModel):
    """Schema for generating Attio person content."""

    spec: AttioPersonSpec
    content: AttioPersonContent


class AttioNoteContent(BaseModel):
    """Content for generated note."""

    title: str = Field(description="Note title")
    content: str = Field(description="Note content with embedded token")
    key_points: List[str] = Field(description="Key points from the note")
