"""ClickUp-specific Pydantic schemas used for LLM structured generation."""

from typing import List
from pydantic import BaseModel, Field
from typing_extensions import Literal


class ClickUpTaskSpec(BaseModel):
    """Specification for a ClickUp task."""

    name: str = Field(description="The task name - should be clear and actionable")
    token: str = Field(description="Unique verification token to embed in the content")
    priority: Literal["low", "normal", "high", "urgent"] = Field(default="normal")
    tags: List[str] = Field(default_factory=list, description="Task tags/labels")


class ClickUpTaskContent(BaseModel):
    """Content for a ClickUp task."""

    description: str = Field(description="Main task description in markdown format")
    objectives: List[str] = Field(description="List of task objectives/requirements")
    technical_details: str = Field(description="Technical implementation details")
    acceptance_criteria: List[str] = Field(description="Definition of done")


class ClickUpTask(BaseModel):
    """Schema for generating ClickUp task content."""

    spec: ClickUpTaskSpec
    content: ClickUpTaskContent


class ClickUpSubtaskSpec(BaseModel):
    """Specification for a ClickUp subtask."""

    name: str = Field(description="The subtask name - should be clear and specific")
    token: str = Field(description="Unique verification token to embed in the content")


class ClickUpSubtaskContent(BaseModel):
    """Content for a ClickUp subtask."""

    description: str = Field(description="Subtask description with implementation details")
    notes: List[str] = Field(description="Additional notes or considerations")


class ClickUpSubtask(BaseModel):
    """Schema for generating ClickUp subtask content."""

    spec: ClickUpSubtaskSpec
    content: ClickUpSubtaskContent


class ClickUpCommentContent(BaseModel):
    """Content for a ClickUp comment."""

    text: str = Field(description="Comment text - should be relevant and helpful")
    token: str = Field(description="Unique verification token to embed in the comment")


class ClickUpFileContent(BaseModel):
    """Content for a ClickUp file attachment."""

    filename: str = Field(description="File name with extension")
    content: str = Field(description="File content - should be relevant to the task")
    token: str = Field(description="Unique verification token to embed in the file")
