"""Airtable-specific Pydantic schemas used for LLM structured generation."""

from typing import List

from pydantic import BaseModel, Field


class AirtableRecordSpec(BaseModel):
    """Specification for an Airtable record."""

    token: str = Field(description="Unique verification token to embed in the content")
    table_name: str = Field(
        default="MonkeTestTable", description="Name of the table (for test tracking)"
    )


class AirtableRecordContent(BaseModel):
    """Content for an Airtable record."""

    primary_field: str = Field(
        description="Primary field value (name/title) - must contain token"
    )
    description: str = Field(description="Description or notes field")
    status: str = Field(
        default="In Progress", description="Status field (e.g., 'In Progress', 'Done')"
    )
    tags: List[str] = Field(
        default_factory=list, description="List of tags or categories"
    )
    notes: str = Field(description="Additional notes or details - must contain token")
    comments: List[str] = Field(
        default_factory=list,
        description="List of 1-2 realistic comments to add to this record - must contain token",
    )


class AirtableRecord(BaseModel):
    """Schema for generating Airtable record content."""

    spec: AirtableRecordSpec
    content: AirtableRecordContent
