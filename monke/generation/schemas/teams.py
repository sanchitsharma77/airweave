"""Microsoft Teams-specific Pydantic schemas used for LLM structured generation."""

from typing import List
from pydantic import BaseModel, Field


class TeamsMessageSpec(BaseModel):
    """Metadata for message generation."""

    token: str = Field(description="Unique verification token to embed in the content")
    importance: str = Field(
        default="normal", description="Importance level (normal, high, urgent)"
    )


class TeamsMessageContent(BaseModel):
    """Content for generated message."""

    subject: str = Field(description="Optional subject line for the message")
    body: str = Field(
        description="Message body content with verification token embedded"
    )
    mentions_context: List[str] = Field(
        default_factory=list,
        description="Context about who/what might be mentioned in the message",
    )


class TeamsMessage(BaseModel):
    """Schema for generating Microsoft Teams message content."""

    spec: TeamsMessageSpec
    content: TeamsMessageContent


class TeamsChannelSpec(BaseModel):
    """Metadata for channel generation."""

    display_name: str = Field(description="Channel display name")
    description: str = Field(description="Channel description")


class TeamsChannel(BaseModel):
    """Schema for generating Microsoft Teams channel."""

    spec: TeamsChannelSpec
