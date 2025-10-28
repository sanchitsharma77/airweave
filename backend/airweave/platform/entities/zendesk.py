"""Zendesk entity schemas."""

from typing import Any, Dict, List, Optional

from airweave.platform.entities._airweave_field import AirweaveField
from airweave.platform.entities._base import BaseEntity, FileEntity


class ZendeskTicketEntity(BaseEntity):
    """Schema for Zendesk ticket entities.

    Reference:
        https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the Zendesk ticket ID)
    # - breadcrumbs (empty - tickets are top-level)
    # - name (from ticket subject)
    # - created_at (from created_at timestamp)
    # - updated_at (from updated_at timestamp)

    # API fields
    ticket_id: int = AirweaveField(
        ..., description="Unique identifier of the ticket", embeddable=False
    )
    subject: str = AirweaveField(..., description="The subject of the ticket", embeddable=True)
    description: Optional[str] = AirweaveField(
        None, description="The description of the ticket (first comment)", embeddable=True
    )
    requester_id: Optional[int] = AirweaveField(
        None, description="ID of the user who requested the ticket", embeddable=False
    )
    requester_name: Optional[str] = AirweaveField(
        None, description="Name of the user who requested the ticket", embeddable=True
    )
    requester_email: Optional[str] = AirweaveField(
        None, description="Email of the user who requested the ticket", embeddable=True
    )
    assignee_id: Optional[int] = AirweaveField(
        None, description="ID of the user assigned to the ticket", embeddable=False
    )
    assignee_name: Optional[str] = AirweaveField(
        None, description="Name of the user assigned to the ticket", embeddable=True
    )
    assignee_email: Optional[str] = AirweaveField(
        None, description="Email of the user assigned to the ticket", embeddable=True
    )
    status: str = AirweaveField(..., description="Current status of the ticket", embeddable=True)
    priority: Optional[str] = AirweaveField(
        None, description="Priority level of the ticket", embeddable=True
    )
    tags: List[str] = AirweaveField(
        default_factory=list, description="Tags associated with the ticket", embeddable=True
    )
    custom_fields: List[Dict[str, Any]] = AirweaveField(
        default_factory=list, description="Custom field values for the ticket", embeddable=False
    )
    organization_id: Optional[int] = AirweaveField(
        None, description="ID of the organization associated with the ticket", embeddable=False
    )
    organization_name: Optional[str] = AirweaveField(
        None, description="Name of the organization associated with the ticket", embeddable=True
    )
    group_id: Optional[int] = AirweaveField(
        None, description="ID of the group the ticket belongs to", embeddable=False
    )
    group_name: Optional[str] = AirweaveField(
        None, description="Name of the group the ticket belongs to", embeddable=True
    )
    ticket_type: Optional[str] = AirweaveField(
        None, description="Type of the ticket (question, incident, problem, task)", embeddable=True
    )
    url: Optional[str] = AirweaveField(
        None, description="URL to view the ticket in Zendesk", embeddable=False
    )


class ZendeskCommentEntity(BaseEntity):
    """Schema for Zendesk comment entities.

    Reference:
        https://developer.zendesk.com/api-reference/ticketing/tickets/ticket-comments/
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (ticket_id_comment_id composite)
    # - breadcrumbs (empty - comments are standalone)
    # - name (from body preview)
    # - created_at (from created_at timestamp)
    # - updated_at (None - comments don't have update timestamp)

    # API fields
    comment_id: int = AirweaveField(
        ..., description="Unique identifier of the comment", embeddable=False
    )
    ticket_id: int = AirweaveField(
        ..., description="ID of the ticket this comment belongs to", embeddable=False
    )
    ticket_subject: str = AirweaveField(
        ..., description="Subject of the ticket this comment belongs to", embeddable=True
    )
    author_id: int = AirweaveField(
        ..., description="ID of the user who wrote the comment", embeddable=False
    )
    author_name: str = AirweaveField(
        ..., description="Name of the user who wrote the comment", embeddable=True
    )
    author_email: Optional[str] = AirweaveField(
        None, description="Email of the user who wrote the comment", embeddable=True
    )
    body: str = AirweaveField(..., description="The content of the comment", embeddable=True)
    html_body: Optional[str] = AirweaveField(
        None, description="HTML formatted content of the comment", embeddable=True
    )
    public: bool = AirweaveField(
        False, description="Whether the comment is public or internal", embeddable=False
    )
    attachments: List[Dict[str, Any]] = AirweaveField(
        default_factory=list,
        description="Attachments associated with this comment",
        embeddable=False,
    )


class ZendeskUserEntity(BaseEntity):
    """Schema for Zendesk user entities.

    Reference:
        https://developer.zendesk.com/api-reference/ticketing/users/users/
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the Zendesk user ID)
    # - breadcrumbs (empty - users are top-level)
    # - name (from user name)
    # - created_at (from created_at timestamp)
    # - updated_at (from updated_at timestamp)

    # API fields
    user_id: int = AirweaveField(..., description="Unique identifier of the user", embeddable=False)
    email: str = AirweaveField(..., description="Email address of the user", embeddable=True)
    role: str = AirweaveField(
        ..., description="Role of the user (end-user, agent, admin)", embeddable=True
    )
    active: bool = AirweaveField(
        ..., description="Whether the user account is active", embeddable=False
    )
    last_login_at: Optional[Any] = AirweaveField(
        None, description="When the user last logged in", embeddable=False
    )
    organization_id: Optional[int] = AirweaveField(
        None, description="ID of the organization the user belongs to", embeddable=False
    )
    organization_name: Optional[str] = AirweaveField(
        None,
        description="Name of the organization the user belongs to",
        embeddable=True,
    )
    phone: Optional[str] = AirweaveField(
        None, description="Phone number of the user", embeddable=True
    )
    time_zone: Optional[str] = AirweaveField(
        None, description="Time zone of the user", embeddable=False
    )
    locale: Optional[str] = AirweaveField(None, description="Locale of the user", embeddable=False)
    custom_fields: List[Dict[str, Any]] = AirweaveField(
        default_factory=list,
        description="Custom field values for the user",
        embeddable=False,
    )
    tags: List[str] = AirweaveField(
        default_factory=list, description="Tags associated with the user", embeddable=True
    )
    user_fields: Dict[str, Any] = AirweaveField(
        default_factory=dict, description="User-specific custom fields", embeddable=False
    )


class ZendeskOrganizationEntity(BaseEntity):
    """Schema for Zendesk organization entities.

    Reference:
        https://developer.zendesk.com/api-reference/ticketing/organizations/organizations/
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the Zendesk organization ID)
    # - breadcrumbs (empty - organizations are top-level)
    # - name (from organization name)
    # - created_at (from created_at timestamp)
    # - updated_at (from updated_at timestamp)

    # API fields
    organization_id: int = AirweaveField(
        ..., description="Unique identifier of the organization", embeddable=False
    )
    domain_names: List[str] = AirweaveField(
        default_factory=list,
        description="Domain names associated with the organization",
        embeddable=True,
    )
    details: Optional[str] = AirweaveField(
        None, description="Details about the organization", embeddable=True
    )
    notes: Optional[str] = AirweaveField(
        None, description="Notes about the organization", embeddable=True
    )
    tags: List[str] = AirweaveField(
        default_factory=list,
        description="Tags associated with the organization",
        embeddable=True,
    )
    custom_fields: List[Dict[str, Any]] = AirweaveField(
        default_factory=list,
        description="Custom field values for the organization",
        embeddable=False,
    )
    organization_fields: Dict[str, Any] = AirweaveField(
        default_factory=dict,
        description="Organization-specific custom fields",
        embeddable=False,
    )


class ZendeskAttachmentEntity(FileEntity):
    """Schema for Zendesk attachment entities.

    Reference:
        https://developer.zendesk.com/api-reference/ticketing/tickets/ticket-attachments/
    """

    # Base fields are inherited from BaseEntity:
    # - entity_id (the Zendesk attachment ID)
    # - breadcrumbs (empty - attachments are standalone)
    # - name (from file_name)
    # - created_at (from created_at timestamp)
    # - updated_at (None - attachments don't have update timestamp)

    # File fields are inherited from FileEntity:
    # - url (download URL)
    # - size (file size in bytes)
    # - file_type (determined from mime_type)
    # - mime_type (from content_type)
    # - local_path (set after download)

    # API fields (Zendesk-specific)
    attachment_id: int = AirweaveField(
        ..., description="Unique identifier of the attachment", embeddable=False
    )
    ticket_id: Optional[int] = AirweaveField(
        None, description="ID of the ticket this attachment belongs to", embeddable=False
    )
    comment_id: Optional[int] = AirweaveField(
        None, description="ID of the comment this attachment belongs to", embeddable=False
    )
    ticket_subject: Optional[str] = AirweaveField(
        None,
        description="Subject of the ticket this attachment belongs to",
        embeddable=True,
    )
    content_type: str = AirweaveField(
        ..., description="MIME type of the attachment", embeddable=False
    )
    file_name: str = AirweaveField(
        ..., description="Original filename of the attachment", embeddable=True
    )
    thumbnails: List[Dict[str, Any]] = AirweaveField(
        default_factory=list,
        description="Thumbnail information for the attachment",
        embeddable=False,
    )
