"""SharePoint entity schemas.

Entity schemas for SharePoint objects based on Microsoft Graph API:
 - User
 - Group
 - Site
 - Drive (document library)
 - DriveItem (file/folder)

Reference:
  https://learn.microsoft.com/en-us/graph/api/resources/sharepoint
  https://learn.microsoft.com/en-us/graph/api/resources/site
  https://learn.microsoft.com/en-us/graph/api/resources/drive
  https://learn.microsoft.com/en-us/graph/api/resources/driveitem
"""

from typing import Any, Dict, List, Optional

from airweave.platform.entities._airweave_field import AirweaveField
from airweave.platform.entities._base import BaseEntity, FileEntity


class SharePointUserEntity(BaseEntity):
    """Schema for a SharePoint user.

    Reference:
        https://learn.microsoft.com/en-us/graph/api/resources/user
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the user ID)
    # - breadcrumbs (empty - users are top-level)
    # - name (from display_name)
    # - created_at (None - users don't have creation timestamp)
    # - updated_at (None - users don't have update timestamp)

    # API fields
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
    mobile_phone: Optional[str] = AirweaveField(
        None, description="The primary cellular telephone number for the user.", embeddable=False
    )
    business_phones: Optional[List[str]] = AirweaveField(
        None, description="The telephone numbers for the user.", embeddable=False
    )
    account_enabled: Optional[bool] = AirweaveField(
        None, description="Whether the account is enabled.", embeddable=False
    )


class SharePointGroupEntity(BaseEntity):
    """Schema for a SharePoint group.

    Reference:
        https://learn.microsoft.com/en-us/graph/api/resources/group
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the group ID)
    # - breadcrumbs (empty - groups are top-level)
    # - name (from display_name)
    # - created_at (from createdDateTime)
    # - updated_at (None - groups don't have update timestamp)

    # API fields
    display_name: Optional[str] = AirweaveField(
        None, description="The display name for the group.", embeddable=True
    )
    description: Optional[str] = AirweaveField(
        None, description="An optional description for the group.", embeddable=True
    )
    mail: Optional[str] = AirweaveField(
        None, description="The SMTP address for the group.", embeddable=True
    )
    mail_enabled: Optional[bool] = AirweaveField(
        None, description="Whether the group is mail-enabled.", embeddable=False
    )
    security_enabled: Optional[bool] = AirweaveField(
        None, description="Whether the group is a security group.", embeddable=False
    )
    group_types: List[str] = AirweaveField(
        default_factory=list,
        description="Specifies the group type (e.g., 'Unified' for Microsoft 365 groups).",
        embeddable=True,
    )
    visibility: Optional[str] = AirweaveField(
        None,
        description="Visibility of the group (Public, Private, HiddenMembership).",
        embeddable=False,
    )


class SharePointSiteEntity(BaseEntity):
    """Schema for a SharePoint site.

    Reference:
        https://learn.microsoft.com/en-us/graph/api/resources/site
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the site ID)
    # - breadcrumbs (empty - sites are top-level)
    # - name (from display_name)
    # - created_at (from createdDateTime)
    # - updated_at (from lastModifiedDateTime)

    # API fields
    display_name: Optional[str] = AirweaveField(
        None, description="The full title for the site.", embeddable=True
    )
    site_name: Optional[str] = AirweaveField(
        None, description="The name/title of the site.", embeddable=True
    )
    description: Optional[str] = AirweaveField(
        None, description="The descriptive text for the site.", embeddable=True
    )
    web_url: Optional[str] = AirweaveField(
        None, description="URL that displays the site in the browser.", embeddable=False
    )
    is_personal_site: Optional[bool] = AirweaveField(
        None, description="Whether the site is a personal site.", embeddable=False
    )
    site_collection: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Details about the site's site collection.", embeddable=False
    )


class SharePointDriveEntity(BaseEntity):
    """Schema for a SharePoint drive (document library).

    Reference:
        https://learn.microsoft.com/en-us/graph/api/resources/drive
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the drive ID)
    # - breadcrumbs (site breadcrumb)
    # - name (from drive name)
    # - created_at (from createdDateTime)
    # - updated_at (from lastModifiedDateTime)

    # API fields
    description: Optional[str] = AirweaveField(
        None, description="User-visible description of the drive.", embeddable=True
    )
    drive_type: Optional[str] = AirweaveField(
        None,
        description="Type of drive (documentLibrary, business, etc.).",
        embeddable=True,
    )
    web_url: Optional[str] = AirweaveField(
        None, description="URL to view the drive in a browser.", embeddable=False
    )
    owner: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Information about the drive's owner.", embeddable=True
    )
    quota: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Information about the drive's storage quota.", embeddable=False
    )
    site_id: Optional[str] = AirweaveField(
        None, description="ID of the site that contains this drive.", embeddable=False
    )


class SharePointDriveItemEntity(FileEntity):
    """Schema for a SharePoint drive item (file or folder).

    Reference:
        https://learn.microsoft.com/en-us/graph/api/resources/driveitem
    """

    # Base fields are inherited from BaseEntity:
    # - entity_id (the drive item ID)
    # - breadcrumbs (site and drive breadcrumbs)
    # - name (from item name)
    # - created_at (from createdDateTime)
    # - updated_at (from lastModifiedDateTime)

    # File fields are inherited from FileEntity:
    # - url (download URL)
    # - size (file size in bytes)
    # - file_type (determined from mime_type)
    # - mime_type
    # - local_path (set after download)

    # API fields (SharePoint-specific)
    description: Optional[str] = AirweaveField(
        None, description="User-visible description of the item.", embeddable=True
    )
    web_url: Optional[str] = AirweaveField(
        None, description="URL to display the item in a browser.", embeddable=False
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
        description="Information about the parent of this item (driveId, path, etc).",
        embeddable=False,
    )
    created_by: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Identity of the user who created the item.", embeddable=True
    )
    last_modified_by: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Identity of the user who last modified the item.", embeddable=True
    )
    site_id: Optional[str] = AirweaveField(
        None, description="ID of the site that contains this item.", embeddable=False
    )
    drive_id: Optional[str] = AirweaveField(
        None, description="ID of the drive that contains this item.", embeddable=False
    )


class SharePointListEntity(BaseEntity):
    """Schema for a SharePoint list.

    Reference:
        https://learn.microsoft.com/en-us/graph/api/resources/list
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the list ID)
    # - breadcrumbs (site breadcrumb)
    # - name (from display_name)
    # - created_at (from createdDateTime)
    # - updated_at (from lastModifiedDateTime)

    # API fields
    display_name: Optional[str] = AirweaveField(
        None, description="The displayable title of the list.", embeddable=True
    )
    list_name: Optional[str] = AirweaveField(
        None, description="The name of the list.", embeddable=True
    )
    description: Optional[str] = AirweaveField(
        None, description="The description of the list.", embeddable=True
    )
    web_url: Optional[str] = AirweaveField(
        None, description="URL to view the list in browser.", embeddable=False
    )
    list_info: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Additional list metadata (template, hidden, etc).", embeddable=False
    )
    site_id: Optional[str] = AirweaveField(
        None, description="ID of the site that contains this list.", embeddable=False
    )


class SharePointListItemEntity(BaseEntity):
    """Schema for a SharePoint list item.

    Reference:
        https://learn.microsoft.com/en-us/graph/api/resources/listitem
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the list item ID)
    # - breadcrumbs (site and list breadcrumbs)
    # - name (from fields data or item ID)
    # - created_at (from createdDateTime)
    # - updated_at (from lastModifiedDateTime)

    # API fields
    fields: Optional[Dict[str, Any]] = AirweaveField(
        None,
        description="The values of the columns set on this list item (dynamic schema).",
        embeddable=True,
    )
    content_type: Optional[Dict[str, Any]] = AirweaveField(
        None, description="The content type of this list item.", embeddable=False
    )
    created_by: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Identity of the user who created the item.", embeddable=True
    )
    last_modified_by: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Identity of the user who last modified the item.", embeddable=True
    )
    web_url: Optional[str] = AirweaveField(
        None, description="URL to view the item in browser.", embeddable=False
    )
    list_id: Optional[str] = AirweaveField(
        None, description="ID of the list that contains this item.", embeddable=False
    )
    site_id: Optional[str] = AirweaveField(
        None, description="ID of the site that contains this item.", embeddable=False
    )


class SharePointPageEntity(BaseEntity):
    """Schema for a SharePoint site page.

    Reference:
        https://learn.microsoft.com/en-us/graph/api/resources/sitepage
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the page ID)
    # - breadcrumbs (site breadcrumb)
    # - name (from title)
    # - created_at (from createdDateTime)
    # - updated_at (from lastModifiedDateTime)

    # API fields
    title: Optional[str] = AirweaveField(
        None, description="The title of the page.", embeddable=True
    )
    page_name: Optional[str] = AirweaveField(
        None, description="The name of the page.", embeddable=True
    )
    content: Optional[str] = AirweaveField(
        None,
        description="The actual page content (extracted from webParts).",
        embeddable=True,
    )
    description: Optional[str] = AirweaveField(
        None, description="Description or summary of the page content.", embeddable=True
    )
    page_layout: Optional[str] = AirweaveField(
        None, description="The layout type of the page (article, home, etc).", embeddable=False
    )
    web_url: Optional[str] = AirweaveField(
        None, description="URL to view the page in browser.", embeddable=False
    )
    created_by: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Identity of the user who created the page.", embeddable=True
    )
    last_modified_by: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Identity of the user who last modified the page.", embeddable=True
    )
    publishing_state: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Publishing status of the page.", embeddable=False
    )
    site_id: Optional[str] = AirweaveField(
        None, description="ID of the site that contains this page.", embeddable=False
    )
