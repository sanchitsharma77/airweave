"""Google Docs entity schemas.

Entity schemas for Google Docs based on Google Drive API.
Google Docs documents are exported as DOCX and represented as FileEntity objects
that get processed through Airweave's file processing pipeline.

References:
    https://developers.google.com/drive/api/v3/reference/files
    https://developers.google.com/drive/api/guides/manage-downloads
"""

from typing import Any, Dict, List, Optional

from airweave.platform.entities._airweave_field import AirweaveField
from airweave.platform.entities._base import FileEntity


class GoogleDocsDocumentEntity(FileEntity):
    """Schema for a Google Docs document.

    Represents a Google Doc file retrieved via the Google Drive API.
    The document content is exported as DOCX and processed through
    Airweave's file processing pipeline to create searchable chunks.

    Reference:
        https://developers.google.com/drive/api/v3/reference/files
        https://developers.google.com/drive/api/guides/manage-downloads
    """

    # Base fields are inherited from BaseEntity:
    # - entity_id (the Google Doc file ID)
    # - breadcrumbs (empty - documents are top-level)
    # - name (filename with .docx extension for processing)
    # - created_at (from created_time)
    # - updated_at (from modified_time)

    # File fields are inherited from FileEntity:
    # - url (web view link)
    # - size (document size in bytes)
    # - file_type (set to "google_doc")
    # - mime_type (DOCX MIME type for export)
    # - local_path (set after download)

    # API fields (Google Docs/Drive-specific)
    title: Optional[str] = AirweaveField(
        None,
        description="Display title of the document (without .docx extension).",
        embeddable=True,
    )
    description: Optional[str] = AirweaveField(
        None, description="Optional description of the document.", embeddable=True
    )
    starred: bool = AirweaveField(
        False, description="Whether the user has starred this document.", embeddable=True
    )
    trashed: bool = AirweaveField(
        False, description="Whether the document is in the trash.", embeddable=False
    )
    explicitly_trashed: bool = AirweaveField(
        False,
        description="Whether the document was explicitly trashed by the user.",
        embeddable=False,
    )
    shared: bool = AirweaveField(
        False, description="Whether the document is shared with others.", embeddable=True
    )
    shared_with_me_time: Optional[Any] = AirweaveField(
        None, description="Time when this document was shared with the user.", embeddable=False
    )
    sharing_user: Optional[Dict[str, Any]] = AirweaveField(
        None, description="User who shared this document.", embeddable=True
    )
    owners: List[Dict[str, Any]] = AirweaveField(
        default_factory=list, description="Owners of the document.", embeddable=True
    )
    permissions: Optional[List[Dict[str, Any]]] = AirweaveField(
        None, description="Permissions for this document.", embeddable=False
    )
    parents: List[str] = AirweaveField(
        default_factory=list,
        description="IDs of parent folders containing this document.",
        embeddable=False,
    )
    web_view_link: Optional[str] = AirweaveField(
        None, description="Link to open the document in Google Docs editor.", embeddable=False
    )
    icon_link: Optional[str] = AirweaveField(
        None, description="Link to the document's icon.", embeddable=False
    )
    created_time: Optional[Any] = AirweaveField(
        None, description="When the document was created.", embeddable=False
    )
    modified_time: Optional[Any] = AirweaveField(
        None, description="When the document was last modified.", embeddable=False
    )
    modified_by_me_time: Optional[Any] = AirweaveField(
        None, description="Last time the user modified the document.", embeddable=False
    )
    viewed_by_me_time: Optional[Any] = AirweaveField(
        None, description="Last time the user viewed the document.", embeddable=False
    )
    version: Optional[int] = AirweaveField(
        None, description="Version number of the document.", embeddable=True
    )
    export_mime_type: Optional[str] = AirweaveField(
        default="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        description="MIME type used for exporting the document content (DOCX).",
        embeddable=False,
    )
