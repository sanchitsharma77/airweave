"""SharePoint-specific Pydantic schemas used for LLM structured generation."""

from typing import Dict, List
from pydantic import BaseModel, Field


class SharePointFileSpec(BaseModel):
    """Metadata for file generation."""

    filename: str = Field(
        description="Name of the file with .txt or .md extension (e.g., 'Project Plan.txt' or 'Project Plan.md')"
    )
    token: str = Field(description="Unique verification token to embed in the content")
    file_type: str = Field(
        default="text/plain",
        description="MIME type: must be 'text/plain' or 'text/markdown' only",
    )


class SharePointFileContent(BaseModel):
    """Content structure for a generated file."""

    title: str = Field(description="Document title/heading")
    content: str = Field(
        description="Main document content with verification token embedded"
    )
    sections: List[str] = Field(
        default_factory=list, description="List of section contents for the document"
    )
    summary: str = Field(default="", description="Brief summary of the document")


class SharePointFile(BaseModel):
    """Complete file structure for generation."""

    spec: SharePointFileSpec
    content: SharePointFileContent


class SharePointFolderSpec(BaseModel):
    """Metadata for folder generation."""

    name: str = Field(description="Name of the folder")
    description: str = Field(default="", description="Folder description")


class SharePointListSpec(BaseModel):
    """Metadata for list generation."""

    display_name: str = Field(description="Display name of the list")
    description: str = Field(description="Description of the list")
    token: str = Field(description="Unique verification token")


class SharePointListItemContent(BaseModel):
    """Content for a list item."""

    title: str = Field(description="Title field with token embedded")
    description: str = Field(description="Description or notes field")
    additional_fields: Dict[str, str] = Field(
        default_factory=dict, description="Additional custom fields"
    )


class SharePointPageContent(BaseModel):
    """Content for a site page."""

    title: str = Field(description="Page title")
    content: str = Field(description="Page content with token embedded")
    description: str = Field(default="", description="Page description/summary")
