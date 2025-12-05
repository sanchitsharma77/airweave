"""Pydantic schemas for Pipedrive test data generation."""

from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class PipedrivePerson(BaseModel):
    """Structured person (contact) content for Pipedrive."""

    token: str = Field(
        description="Verification token that MUST appear in the name or organization."
    )
    name: str = Field(description="Full name of the person")
    email: EmailStr = Field(description="Email address")
    phone: Optional[str] = Field(default=None, description="Phone number")
    org_name: Optional[str] = Field(default=None, description="Organization name")


class PipedriveOrganization(BaseModel):
    """Structured organization (company) content for Pipedrive."""

    token: str = Field(
        description="Verification token that MUST appear in the organization name."
    )
    name: str = Field(description="Organization name")
    address: Optional[str] = Field(default=None, description="Business address")


class PipedriveDeal(BaseModel):
    """Structured deal content for Pipedrive."""

    token: str = Field(description="Verification token that MUST appear in the title.")
    title: str = Field(description="Deal title")
    value: Optional[float] = Field(default=None, description="Deal value")
    currency: str = Field(default="USD", description="Currency code")


class PipedriveActivity(BaseModel):
    """Structured activity content for Pipedrive (calls, meetings, tasks)."""

    token: str = Field(
        description="Verification token that MUST appear in the subject."
    )
    subject: str = Field(description="Activity subject/title")
    activity_type: str = Field(
        default="task",
        description="Type of activity (call, meeting, task, deadline, email, lunch)",
    )
    note: Optional[str] = Field(default=None, description="Activity note/description")
    due_date: Optional[str] = Field(
        default=None, description="Due date in YYYY-MM-DD format"
    )
    due_time: Optional[str] = Field(default=None, description="Due time in HH:MM format")
    duration: Optional[str] = Field(
        default=None, description="Duration in HH:MM format"
    )


class PipedriveProduct(BaseModel):
    """Structured product content for Pipedrive."""

    token: str = Field(
        description="Verification token that MUST appear in the product name."
    )
    name: str = Field(description="Product name")
    code: Optional[str] = Field(default=None, description="Product code/SKU")
    description: Optional[str] = Field(default=None, description="Product description")
    unit: Optional[str] = Field(default="piece", description="Unit of measurement")
    price: Optional[float] = Field(default=None, description="Product price")
    currency: str = Field(default="USD", description="Currency code")


class PipedriveLead(BaseModel):
    """Structured lead content for Pipedrive."""

    token: str = Field(
        description="Verification token that MUST appear in the lead title."
    )
    title: str = Field(description="Lead title")
    value: Optional[float] = Field(default=None, description="Expected lead value")
    currency: str = Field(default="USD", description="Currency code")


class PipedriveNote(BaseModel):
    """Structured note content for Pipedrive."""

    token: str = Field(
        description="Verification token that MUST appear in the note content."
    )
    content: str = Field(description="Note content/body")
