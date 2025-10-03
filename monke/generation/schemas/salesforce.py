from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class SalesforceContact(BaseModel):
    """Structured contact content for Salesforce."""

    token: str = Field(
        description="Verification token that MUST appear in at least one property (e.g., email)."
    )
    email: EmailStr
    first_name: str
    last_name: str
    phone: Optional[str] = None
    mobile_phone: Optional[str] = None
    title: Optional[str] = None
    department: Optional[str] = None
    description: Optional[str] = None
    mailing_street: Optional[str] = None
    mailing_city: Optional[str] = None
    mailing_state: Optional[str] = None
    mailing_postal_code: Optional[str] = None
    mailing_country: Optional[str] = None
    notes: Optional[str] = None  # not posted to Salesforce; useful context
