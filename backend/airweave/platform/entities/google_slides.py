"""Google Slides entity schemas.

Entity schemas for Google Slides based on Google Slides API and Google Drive API.
Google Slides presentations are exported as PDF/PPTX and represented as FileEntity objects
that get processed through Airweave's file processing pipeline.

References:
    https://developers.google.com/slides/api/reference/rest
    https://developers.google.com/drive/api/v3/reference/files
    https://developers.google.com/drive/api/guides/manage-downloads
"""

from typing import Any, Dict, List, Optional

from airweave.platform.entities._airweave_field import AirweaveField
from airweave.platform.entities._base import BaseEntity, FileEntity


class GoogleSlidesPresentationEntity(FileEntity):
    """Schema for a Google Slides presentation.

    Represents a Google Slides presentation retrieved via the Google Drive API.
    The presentation content is exported as PDF and processed through
    Airweave's file processing pipeline to create searchable chunks.

    Reference:
        https://developers.google.com/slides/api/reference/rest/v1/presentations
        https://developers.google.com/drive/api/v3/reference/files
    """

    # Base fields are inherited from BaseEntity:
    # - entity_id (the Google Slides presentation file ID)
    # - breadcrumbs (empty - presentations are top-level)
    # - name (filename with .pdf extension for processing)
    # - created_at (from created_time)
    # - updated_at (from modified_time)

    # File fields are inherited from FileEntity:
    # - url (web view link)
    # - size (presentation size in bytes)
    # - file_type (set to "google_slides")
    # - mime_type (PDF MIME type for export)
    # - local_path (set after download)

    # API fields (Google Slides/Drive-specific)
    title: Optional[str] = AirweaveField(
        None,
        description="Display title of the presentation (without file extension).",
        embeddable=True,
    )
    description: Optional[str] = AirweaveField(
        None, description="Optional description of the presentation.", embeddable=True
    )
    starred: bool = AirweaveField(
        False, description="Whether the user has starred this presentation.", embeddable=True
    )
    trashed: bool = AirweaveField(
        False, description="Whether the presentation is in the trash.", embeddable=False
    )
    explicitly_trashed: bool = AirweaveField(
        False,
        description="Whether the presentation was explicitly trashed by the user.",
        embeddable=False,
    )
    shared: bool = AirweaveField(
        False, description="Whether the presentation is shared with others.", embeddable=True
    )
    shared_with_me_time: Optional[Any] = AirweaveField(
        None, description="Time when this presentation was shared with the user.", embeddable=False
    )
    sharing_user: Optional[Dict[str, Any]] = AirweaveField(
        None, description="User who shared this presentation.", embeddable=True
    )
    owners: List[Dict[str, Any]] = AirweaveField(
        default_factory=list, description="Owners of the presentation.", embeddable=True
    )
    permissions: Optional[List[Dict[str, Any]]] = AirweaveField(
        None, description="Permissions for this presentation.", embeddable=False
    )
    parents: List[str] = AirweaveField(
        default_factory=list,
        description="IDs of parent folders containing this presentation.",
        embeddable=False,
    )
    web_view_link: Optional[str] = AirweaveField(
        None, description="Link to open the presentation in Google Slides editor.", embeddable=False
    )
    icon_link: Optional[str] = AirweaveField(
        None, description="Link to the presentation's icon.", embeddable=False
    )
    created_time: Optional[Any] = AirweaveField(
        None, description="When the presentation was created.", embeddable=False
    )
    modified_time: Optional[Any] = AirweaveField(
        None, description="When the presentation was last modified.", embeddable=False
    )
    modified_by_me_time: Optional[Any] = AirweaveField(
        None, description="Last time the user modified the presentation.", embeddable=False
    )
    viewed_by_me_time: Optional[Any] = AirweaveField(
        None, description="Last time the user viewed the presentation.", embeddable=False
    )
    version: Optional[int] = AirweaveField(
        None, description="Version number of the presentation.", embeddable=True
    )
    slide_count: Optional[int] = AirweaveField(
        None, description="Number of slides in the presentation.", embeddable=True
    )
    locale: Optional[str] = AirweaveField(
        None, description="The locale of the presentation.", embeddable=True
    )
    revision_id: Optional[str] = AirweaveField(
        None, description="The revision ID of the presentation.", embeddable=False
    )
    export_mime_type: Optional[str] = AirweaveField(
        default="application/pdf",
        description="MIME type used for exporting the presentation content (PDF).",
        embeddable=False,
    )


class GoogleSlidesSlideEntity(BaseEntity):
    """Schema for a Google Slides slide.

    Represents an individual slide within a Google Slides presentation.
    This entity captures slide-specific metadata and content for detailed
    indexing and search capabilities.

    Reference:
        https://developers.google.com/slides/api/reference/rest/v1/presentations.pages
    """

    # Base fields are inherited from BaseEntity:
    # - entity_id (the slide ID)
    # - breadcrumbs (presentation breadcrumb)
    # - name (slide title or "Slide {number}")
    # - created_at (from created_time if available)
    # - updated_at (from modified_time if available)

    # API fields
    slide_id: str = AirweaveField(
        ..., description="Unique ID of the slide within the presentation.", embeddable=False
    )
    presentation_id: str = AirweaveField(
        ..., description="ID of the parent presentation containing this slide.", embeddable=False
    )
    slide_number: int = AirweaveField(
        ..., description="The zero-based index of the slide in the presentation.", embeddable=True
    )
    title: Optional[str] = AirweaveField(
        None, description="Title of the slide if available.", embeddable=True
    )
    notes: Optional[str] = AirweaveField(
        None, description="Speaker notes for the slide.", embeddable=True
    )
    layout_type: Optional[str] = AirweaveField(
        None, description="The type of slide layout.", embeddable=False
    )
    master_properties: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Properties of the slide master.", embeddable=False
    )
    elements: List[Dict[str, Any]] = AirweaveField(
        default_factory=list, description="List of elements on the slide.", embeddable=False
    )
    text_content: Optional[str] = AirweaveField(
        None, description="Extracted text content from all elements on the slide.", embeddable=True
    )
    background: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Background properties of the slide.", embeddable=False
    )
    color_scheme: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Color scheme of the slide.", embeddable=False
    )
    created_time: Optional[Any] = AirweaveField(
        None, description="When the slide was created.", embeddable=False
    )
    modified_time: Optional[Any] = AirweaveField(
        None, description="When the slide was last modified.", embeddable=False
    )
    presentation_title: Optional[str] = AirweaveField(
        None, description="Title of the parent presentation.", embeddable=True
    )
    presentation_url: Optional[str] = AirweaveField(
        None, description="URL to view the parent presentation.", embeddable=False
    )
