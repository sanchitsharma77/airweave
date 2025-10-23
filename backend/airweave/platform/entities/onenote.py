"""Microsoft OneNote entity schemas.

Entity schemas for Microsoft OneNote objects based on Microsoft Graph API:
 - Notebook (top-level container)
 - Section Group (organizational container)
 - Section (contains pages)
 - Page (content pages)
 - User (notebook owners/contributors)

Reference:
  https://learn.microsoft.com/en-us/graph/api/resources/onenote
  https://learn.microsoft.com/en-us/graph/api/resources/notebook
  https://learn.microsoft.com/en-us/graph/api/resources/section
  https://learn.microsoft.com/en-us/graph/api/resources/onenotepage
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from airweave.platform.entities._airweave_field import AirweaveField
from airweave.platform.entities._base import ChunkEntity, FileEntity


class OneNoteUserEntity(ChunkEntity):
    """Schema for a Microsoft OneNote user.

    Represents a user who owns or has access to OneNote notebooks.
    Based on the Microsoft Graph user resource.

    Reference: https://learn.microsoft.com/en-us/graph/api/resources/user
    """

    display_name: Optional[str] = AirweaveField(
        None, description="The name displayed in the address book for the user.", embeddable=True
    )
    user_principal_name: Optional[str] = AirweaveField(
        None,
        description="The user principal name (UPN) of the user (e.g., user@contoso.com).",
        embeddable=True,
    )
    mail: Optional[str] = AirweaveField(
        None, description="The SMTP address for the user.", embeddable=True
    )
    job_title: Optional[str] = AirweaveField(
        None, description="The user's job title.", embeddable=True
    )
    department: Optional[str] = AirweaveField(
        None, description="The department in which the user works.", embeddable=True
    )
    office_location: Optional[str] = AirweaveField(
        None, description="The office location in the user's place of business.", embeddable=True
    )


class OneNoteNotebookEntity(ChunkEntity):
    """Schema for a Microsoft OneNote notebook.

    Based on the Microsoft Graph notebook resource.
    Reference: https://learn.microsoft.com/en-us/graph/api/resources/notebook
    """

    display_name: str = AirweaveField(..., description="The name of the notebook.", embeddable=True)
    name: str = AirweaveField(
        ..., description="The name of the notebook (alias for display_name).", embeddable=True
    )
    is_default: Optional[bool] = AirweaveField(
        None, description="Indicates whether this is the user's default notebook."
    )
    is_shared: Optional[bool] = AirweaveField(
        None, description="Indicates whether the notebook is shared with other users."
    )
    user_role: Optional[str] = AirweaveField(
        None,
        description="The current user's role in the notebook (Owner, Contributor, Reader).",
        embeddable=True,
    )
    created_datetime: Optional[datetime] = AirweaveField(
        None,
        description="Timestamp at which the notebook was created.",
        is_created_at=True,
        embeddable=True,
    )
    last_modified_datetime: Optional[datetime] = AirweaveField(
        None,
        description="Timestamp at which the notebook was last modified.",
        is_updated_at=True,
        embeddable=True,
    )
    created_by: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Identity of the user who created the notebook.", embeddable=True
    )
    last_modified_by: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Identity of the user who last modified the notebook.", embeddable=True
    )
    links: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Links for opening the notebook.", embeddable=False
    )
    self_url: Optional[str] = AirweaveField(
        None, description="The endpoint URL where you can get details about the notebook."
    )


class OneNoteSectionGroupEntity(ChunkEntity):
    """Schema for a Microsoft OneNote section group.

    Section groups are containers that can hold sections and other section groups.
    Based on the Microsoft Graph sectionGroup resource.

    Reference: https://learn.microsoft.com/en-us/graph/api/resources/sectiongroup
    """

    notebook_id: str = AirweaveField(
        ..., description="ID of the notebook this section group belongs to."
    )
    parent_section_group_id: Optional[str] = AirweaveField(
        None, description="ID of the parent section group, if nested."
    )
    display_name: str = AirweaveField(
        ..., description="The name of the section group.", embeddable=True
    )
    name: str = AirweaveField(
        ..., description="The name of the section group (alias for display_name).", embeddable=True
    )
    created_datetime: Optional[datetime] = AirweaveField(
        None,
        description="Timestamp at which the section group was created.",
        is_created_at=True,
        embeddable=True,
    )
    last_modified_datetime: Optional[datetime] = AirweaveField(
        None,
        description="Timestamp at which the section group was last modified.",
        is_updated_at=True,
        embeddable=True,
    )
    created_by: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Identity of the user who created the section group.", embeddable=True
    )
    last_modified_by: Optional[Dict[str, Any]] = AirweaveField(
        None,
        description="Identity of the user who last modified the section group.",
        embeddable=True,
    )
    sections_url: Optional[str] = AirweaveField(
        None,
        description="The endpoint URL where you can get all the sections in the section group.",
    )
    section_groups_url: Optional[str] = AirweaveField(
        None,
        description="The endpoint URL where you can get all the section groups "
        "nested in this section group.",
    )


class OneNoteSectionEntity(ChunkEntity):
    """Schema for a Microsoft OneNote section.

    Sections contain pages and can belong to a notebook or section group.
    Based on the Microsoft Graph onenoteSection resource.

    Reference: https://learn.microsoft.com/en-us/graph/api/resources/section
    """

    notebook_id: str = AirweaveField(..., description="ID of the notebook this section belongs to.")
    parent_section_group_id: Optional[str] = AirweaveField(
        None, description="ID of the parent section group, if any."
    )
    display_name: str = AirweaveField(..., description="The name of the section.", embeddable=True)
    name: str = AirweaveField(
        ..., description="The name of the section (alias for display_name).", embeddable=True
    )
    is_default: Optional[bool] = AirweaveField(
        None, description="Indicates whether this is the user's default section."
    )
    created_datetime: Optional[datetime] = AirweaveField(
        None,
        description="Timestamp at which the section was created.",
        is_created_at=True,
        embeddable=True,
    )
    last_modified_datetime: Optional[datetime] = AirweaveField(
        None,
        description="Timestamp at which the section was last modified.",
        is_updated_at=True,
        embeddable=True,
    )
    created_by: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Identity of the user who created the section.", embeddable=True
    )
    last_modified_by: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Identity of the user who last modified the section.", embeddable=True
    )
    pages_url: Optional[str] = AirweaveField(
        None, description="The endpoint URL where you can get all the pages in the section."
    )


class OneNotePageFileEntity(FileEntity):
    """Schema for a Microsoft OneNote page as a file entity.

    Pages are the actual content containers in OneNote.
    Based on the Microsoft Graph onenotePage resource.
    Extends FileEntity to leverage Airweave's HTML processing pipeline.

    Reference: https://learn.microsoft.com/en-us/graph/api/resources/onenotepage
    """

    notebook_id: str = AirweaveField(..., description="ID of the notebook this page belongs to.")
    section_id: str = AirweaveField(..., description="ID of the section this page belongs to.")
    title: str = AirweaveField(..., description="The title of the page.", embeddable=True)
    content_url: Optional[str] = AirweaveField(
        None, description="The URL for the page's HTML content."
    )
    level: Optional[int] = AirweaveField(
        None, description="The indentation level of the page (for hierarchical pages)."
    )
    order: Optional[int] = AirweaveField(
        None, description="The order of the page within its parent section."
    )
    created_datetime: Optional[datetime] = AirweaveField(
        None,
        description="Timestamp at which the page was created.",
        is_created_at=True,
        embeddable=True,
    )
    last_modified_datetime: Optional[datetime] = AirweaveField(
        None,
        description="Timestamp at which the page was last modified.",
        is_updated_at=True,
        embeddable=True,
    )
    created_by: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Identity of the user who created the page.", embeddable=True
    )
    last_modified_by: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Identity of the user who last modified the page.", embeddable=True
    )
    links: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Links for opening the page in OneNote client or web."
    )
    user_tags: Optional[List[str]] = AirweaveField(
        default_factory=list,
        description="User-defined tags associated with the page.",
        embeddable=True,
    )

    def __init__(self, **data):
        """Initialize the entity and set file_type and mime_type for HTML processing."""
        # Set HTML-specific values for OneNote pages
        data.setdefault("mime_type", "text/html")
        data.setdefault("file_type", "html")
        data.setdefault("download_url", data.get("content_url", ""))
        data.setdefault("file_id", data.get("entity_id", ""))

        # Ensure name has .html extension for proper file processing
        title = data.get("title", "Untitled Page")
        if not title.endswith(".html"):
            title = f"{title}.html"
        data.setdefault("name", title)

        super().__init__(**data)
