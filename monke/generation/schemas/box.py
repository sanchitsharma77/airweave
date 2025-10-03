"""Pydantic schemas for Box test content generation."""

from pydantic import BaseModel, Field


class FolderContent(BaseModel):
    """Content structure for a generated folder."""

    description: str = Field(
        ..., description="Folder description with verification token embedded"
    )
    purpose: str = Field(..., description="Purpose of the folder")
    project_info: str = Field(
        ..., description="Project information related to this folder"
    )


class FolderSpec(BaseModel):
    """Metadata for folder generation."""

    name: str = Field(..., description="Folder name")
    token: str = Field(..., description="Verification token to embed")


class BoxFolder(BaseModel):
    """Complete folder structure for generation."""

    spec: FolderSpec
    content: FolderContent


class FileContent(BaseModel):
    """Content structure for a generated file."""

    content: str = Field(
        ..., description="File content with verification token embedded"
    )
    filename: str = Field(..., description="Name of the file")
    description: str = Field(..., description="File description")


class FileSpec(BaseModel):
    """Metadata for file generation."""

    token: str = Field(..., description="Verification token to embed")
    file_extension: str = Field(
        default=".txt", description="File extension (e.g. .txt, .md)"
    )


class BoxFile(BaseModel):
    """Complete file structure for generation."""

    spec: FileSpec
    content: FileContent


class CommentContent(BaseModel):
    """Content structure for a generated comment."""

    message: str = Field(
        ..., description="Comment text with verification token embedded"
    )
    author_name: str = Field(default="Test User", description="Name of comment author")


class CommentSpec(BaseModel):
    """Metadata for comment generation."""

    token: str = Field(..., description="Verification token to embed")


class BoxComment(BaseModel):
    """Complete comment structure for generation."""

    spec: CommentSpec
    content: CommentContent
