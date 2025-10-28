"""Microsoft Word entity schemas.

Entity schemas for Microsoft Word documents based on Microsoft Graph API:
 - WordDocument (Word file with full metadata)

Reference:
  https://learn.microsoft.com/en-us/graph/api/resources/driveitem
  https://learn.microsoft.com/en-us/graph/api/driveitem-get-content
"""

from typing import Any, Dict, Optional

from airweave.platform.entities._airweave_field import AirweaveField
from airweave.platform.entities._base import FileEntity


class WordDocumentEntity(FileEntity):
    """Schema for a Microsoft Word document as a file entity.

    Represents Word documents (.docx, .doc) stored in OneDrive/SharePoint.
    Extends FileEntity to leverage Airweave's file processing pipeline which will:
    - Download the Word document
    - Convert it to markdown using document converters
    - Chunk the content for indexing

    Reference:
        https://learn.microsoft.com/en-us/graph/api/resources/driveitem
    """

    # Base fields are inherited from BaseEntity:
    # - entity_id (the Word document ID)
    # - breadcrumbs (empty - documents are top-level)
    # - name (from filename with extension)
    # - created_at (from created_datetime)
    # - updated_at (from last_modified_datetime)

    # File fields are inherited from FileEntity:
    # - url (download URL)
    # - size (file size in bytes)
    # - file_type (set to "microsoft_word_doc")
    # - mime_type (Word MIME type)
    # - local_path (set after download)

    # API fields (Word/OneDrive-specific)
    title: str = AirweaveField(..., description="The title/name of the document.", embeddable=True)
    web_url: Optional[str] = AirweaveField(
        None, description="URL to open the document in Word Online.", embeddable=False
    )
    content_download_url: Optional[str] = AirweaveField(
        None, description="Direct download URL for the document content.", embeddable=False
    )
    created_by: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Identity of the user who created the document.", embeddable=True
    )
    last_modified_by: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Identity of the user who last modified the document.", embeddable=True
    )
    parent_reference: Optional[Dict[str, Any]] = AirweaveField(
        None,
        description="Information about the parent folder/drive location.",
        embeddable=False,
    )
    drive_id: Optional[str] = AirweaveField(
        None, description="ID of the drive containing this document.", embeddable=False
    )
    folder_path: Optional[str] = AirweaveField(
        None, description="Full path to the parent folder.", embeddable=True
    )
    description: Optional[str] = AirweaveField(
        None, description="Description of the document if available.", embeddable=True
    )
    shared: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Information about sharing status of the document.", embeddable=True
    )
