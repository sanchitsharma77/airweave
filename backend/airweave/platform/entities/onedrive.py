"""OneDrive entity schemas.

Based on the Microsoft Graph API reference for OneDrive,
we define entity schemas for the following core objects:
  • Drive
  • DriveItem

References:
  https://learn.microsoft.com/en-us/graph/api/resources/drive?view=graph-rest-1.0
  https://learn.microsoft.com/en-us/graph/api/resources/driveitem?view=graph-rest-1.0
"""

from typing import Any, Dict, Optional

from airweave.platform.entities._airweave_field import AirweaveField
from airweave.platform.entities._base import BaseEntity, FileEntity


class OneDriveDriveEntity(BaseEntity):
    """Schema for a OneDrive Drive object.

    Reference:
        https://learn.microsoft.com/en-us/graph/api/resources/drive?view=graph-rest-1.0
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the drive ID)
    # - breadcrumbs (empty - drives are top-level)
    # - name (from drive name or drive_type)
    # - created_at (from createdDateTime timestamp)
    # - updated_at (from lastModifiedDateTime timestamp)

    # API fields
    drive_type: Optional[str] = AirweaveField(
        None,
        description=(
            "Describes the type of drive represented by this resource "
            "(e.g., personal, business, documentLibrary)."
        ),
        embeddable=True,
    )
    owner: Optional[Dict[str, Any]] = AirweaveField(
        None,
        description="Information about the user or application that owns this drive.",
        embeddable=True,
    )
    quota: Optional[Dict[str, Any]] = AirweaveField(
        None,
        description="Information about the drive's storage quota (total, used, remaining, etc.).",
        embeddable=False,
    )


class OneDriveDriveItemEntity(FileEntity):
    """Schema for a OneDrive DriveItem object (file or folder).

    Inherits from FileEntity to support file processing capabilities.

    Reference:
        https://learn.microsoft.com/en-us/graph/api/resources/driveitem?view=graph-rest-1.0
    """

    # Base fields are inherited from BaseEntity:
    # - entity_id (the DriveItem ID)
    # - breadcrumbs (drive breadcrumb)
    # - name (from item name)
    # - created_at (from createdDateTime timestamp)
    # - updated_at (from lastModifiedDateTime timestamp)

    # File fields are inherited from FileEntity:
    # - url (download URL)
    # - size (file size in bytes)
    # - file_type (determined from mime_type)
    # - mime_type
    # - local_path (set after download)

    # API fields (OneDrive-specific)
    description: Optional[str] = AirweaveField(
        None, description="Description of the item (if available).", embeddable=True
    )
    etag: Optional[str] = AirweaveField(
        None,
        description="An eTag for the content of the item. Used for change tracking.",
        embeddable=False,
    )
    ctag: Optional[str] = AirweaveField(
        None,
        description="A cTag for the content of the item. Used for internal sync.",
        embeddable=False,
    )
    web_url: Optional[str] = AirweaveField(
        None, description="URL that displays the resource in the browser.", embeddable=False
    )
    file: Optional[Dict[str, Any]] = AirweaveField(
        None,
        description="File metadata if the item is a file (e.g., mimeType, hashes).",
        embeddable=False,
    )
    folder: Optional[Dict[str, Any]] = AirweaveField(
        None,
        description="Folder metadata if the item is a folder (e.g., childCount).",
        embeddable=False,
    )
    parent_reference: Optional[Dict[str, Any]] = AirweaveField(
        None,
        description=(
            "Information about the parent of this item, such as driveId or parent folder path."
        ),
        embeddable=False,
    )
