"""Microsoft OneNote entity schemas.

Entity schemas for Microsoft OneNote objects based on Microsoft Graph API:
 - Notebook (top-level container)
 - Section (contains pages)
 - Page (content pages)

Reference:
  https://learn.microsoft.com/en-us/graph/api/resources/onenote
  https://learn.microsoft.com/en-us/graph/api/resources/notebook
  https://learn.microsoft.com/en-us/graph/api/resources/section
  https://learn.microsoft.com/en-us/graph/api/resources/onenotepage
"""

from typing import Any, Dict, List, Optional

from airweave.platform.entities._airweave_field import AirweaveField
from airweave.platform.entities._base import BaseEntity, FileEntity


class OneNoteNotebookEntity(BaseEntity):
    """Schema for a Microsoft OneNote notebook.

    Reference:
        https://learn.microsoft.com/en-us/graph/api/resources/notebook
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the notebook ID)
    # - breadcrumbs (empty - notebooks are top-level)
    # - name (from display_name)
    # - created_at (from created_datetime)
    # - updated_at (from last_modified_datetime)

    # API fields
    display_name: str = AirweaveField(..., description="The name of the notebook.", embeddable=True)
    is_default: Optional[bool] = AirweaveField(
        None, description="Indicates whether this is the user's default notebook.", embeddable=False
    )
    is_shared: Optional[bool] = AirweaveField(
        None,
        description="Indicates whether the notebook is shared with other users.",
        embeddable=False,
    )
    user_role: Optional[str] = AirweaveField(
        None,
        description="The current user's role in the notebook (Owner, Contributor, Reader).",
        embeddable=True,
    )
    created_by: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Identity of the user who created the notebook.", embeddable=True
    )
    last_modified_by: Optional[Dict[str, Any]] = AirweaveField(
        None,
        description="Identity of the user who last modified the notebook.",
        embeddable=True,
    )
    links: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Links for opening the notebook.", embeddable=False
    )
    self_url: Optional[str] = AirweaveField(
        None,
        description="The endpoint URL where you can get details about the notebook.",
        embeddable=False,
    )


class OneNoteSectionGroupEntity(BaseEntity):
    """Schema for a Microsoft OneNote section group.

    Section groups are containers that can hold sections and other section groups.

    Reference:
        https://learn.microsoft.com/en-us/graph/api/resources/sectiongroup
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the section group ID)
    # - breadcrumbs (notebook breadcrumb)
    # - name (from display_name)
    # - created_at (from created_datetime)
    # - updated_at (from last_modified_datetime)

    # API fields
    notebook_id: str = AirweaveField(
        ..., description="ID of the notebook this section group belongs to.", embeddable=False
    )
    parent_section_group_id: Optional[str] = AirweaveField(
        None, description="ID of the parent section group, if nested.", embeddable=False
    )
    display_name: str = AirweaveField(
        ..., description="The name of the section group.", embeddable=True
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
        description=("The endpoint URL where you can get all the sections in the section group."),
        embeddable=False,
    )
    section_groups_url: Optional[str] = AirweaveField(
        None,
        description=(
            "The endpoint URL where you can get all the section groups "
            "nested in this section group."
        ),
        embeddable=False,
    )


class OneNoteSectionEntity(BaseEntity):
    """Schema for a Microsoft OneNote section.

    Sections contain pages and can belong to a notebook or section group.

    Reference:
        https://learn.microsoft.com/en-us/graph/api/resources/section
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the section ID)
    # - breadcrumbs (notebook breadcrumb)
    # - name (from display_name)
    # - created_at (from created_datetime)
    # - updated_at (from last_modified_datetime)

    # API fields
    notebook_id: str = AirweaveField(
        ..., description="ID of the notebook this section belongs to.", embeddable=False
    )
    parent_section_group_id: Optional[str] = AirweaveField(
        None, description="ID of the parent section group, if any.", embeddable=False
    )
    display_name: str = AirweaveField(..., description="The name of the section.", embeddable=True)
    is_default: Optional[bool] = AirweaveField(
        None, description="Indicates whether this is the user's default section.", embeddable=False
    )
    created_by: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Identity of the user who created the section.", embeddable=True
    )
    last_modified_by: Optional[Dict[str, Any]] = AirweaveField(
        None,
        description="Identity of the user who last modified the section.",
        embeddable=True,
    )
    pages_url: Optional[str] = AirweaveField(
        None,
        description="The endpoint URL where you can get all the pages in the section.",
        embeddable=False,
    )


class OneNotePageFileEntity(FileEntity):
    """Schema for a Microsoft OneNote page as a file entity.

    Pages are the actual content containers in OneNote.
    Extends FileEntity to leverage Airweave's HTML processing pipeline.

    Reference:
        https://learn.microsoft.com/en-us/graph/api/resources/onenotepage
    """

    # Base fields are inherited from BaseEntity:
    # - entity_id (the page ID)
    # - breadcrumbs (notebook and section breadcrumbs)
    # - name (from title with .html extension)
    # - created_at (from created_datetime)
    # - updated_at (from last_modified_datetime)

    # File fields are inherited from FileEntity:
    # - url (content URL)
    # - size (0 - content downloaded)
    # - file_type (set to "html")
    # - mime_type (set to "text/html")
    # - local_path (set after download)

    # API fields (OneNote-specific)
    notebook_id: str = AirweaveField(
        ..., description="ID of the notebook this page belongs to.", embeddable=False
    )
    section_id: str = AirweaveField(
        ..., description="ID of the section this page belongs to.", embeddable=False
    )
    title: str = AirweaveField(..., description="The title of the page.", embeddable=True)
    content_url: Optional[str] = AirweaveField(
        None, description="The URL for the page's HTML content.", embeddable=False
    )
    level: Optional[int] = AirweaveField(
        None,
        description="The indentation level of the page (for hierarchical pages).",
        embeddable=False,
    )
    order: Optional[int] = AirweaveField(
        None, description="The order of the page within its parent section.", embeddable=False
    )
    created_by: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Identity of the user who created the page.", embeddable=True
    )
    last_modified_by: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Identity of the user who last modified the page.", embeddable=True
    )
    links: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Links for opening the page in OneNote client or web.", embeddable=False
    )
    user_tags: Optional[List[str]] = AirweaveField(
        default_factory=list,
        description="User-defined tags associated with the page.",
        embeddable=True,
    )
