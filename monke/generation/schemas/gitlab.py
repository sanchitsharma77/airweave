"""GitLab-specific Pydantic schemas used for LLM structured generation."""

from typing import List
from pydantic import BaseModel, Field


class GitLabIssueSpec(BaseModel):
    """Metadata for GitLab issue generation."""

    title: str = Field(description="The issue title - should be clear and actionable")
    token: str = Field(description="Unique verification token to embed in the content")
    labels: List[str] = Field(default_factory=list, description="Issue labels")


class GitLabIssueContent(BaseModel):
    """Content structure for a generated GitLab issue."""

    description: str = Field(description="Main issue description in markdown format")
    acceptance_criteria: List[str] = Field(description="Definition of done")
    comments: List[str] = Field(description="Initial comments to add to the issue")


class GitLabIssue(BaseModel):
    """Schema for generating GitLab issue content."""

    spec: GitLabIssueSpec
    content: GitLabIssueContent


class GitLabMergeRequestSpec(BaseModel):
    """Metadata for GitLab merge request generation."""

    title: str = Field(description="The merge request title")
    token: str = Field(description="Unique verification token to embed in the content")
    source_branch: str = Field(description="Source branch name")
    target_branch: str = Field(default="main", description="Target branch name")


class GitLabMergeRequestContent(BaseModel):
    """Content structure for a generated GitLab merge request."""

    description: str = Field(
        description="Main merge request description in markdown format"
    )
    changes: List[str] = Field(description="List of changes made")
    comments: List[str] = Field(
        description="Initial comments to add to the merge request"
    )


class GitLabMergeRequest(BaseModel):
    """Schema for generating GitLab merge request content."""

    spec: GitLabMergeRequestSpec
    content: GitLabMergeRequestContent


class GitLabFileContent(BaseModel):
    """Content structure for a generated file."""

    content: str = Field(description="File content with verification token embedded")

    filename: str = Field(description="Name of the file")
