"""Outlook Calendar entity schemas.

Comprehensive schemas based on the Microsoft Graph API Calendar and Event resources.

Reference:
  https://learn.microsoft.com/en-us/graph/api/resources/calendar?view=graph-rest-1.0
  https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0
"""

from typing import Any, Dict, List, Optional

from airweave.platform.entities._airweave_field import AirweaveField
from airweave.platform.entities._base import BaseEntity, FileEntity


class OutlookCalendarCalendarEntity(BaseEntity):
    """Schema for an Outlook Calendar object.

    Reference:
        https://learn.microsoft.com/en-us/graph/api/resources/calendar?view=graph-rest-1.0
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the calendar ID)
    # - breadcrumbs (empty - calendars are top-level)
    # - name (from calendar name)
    # - created_at (None - calendars don't have creation timestamp)
    # - updated_at (None - calendars don't have update timestamp)

    # API fields
    color: Optional[str] = AirweaveField(
        None,
        description="Color theme to distinguish the calendar (auto, lightBlue, etc.).",
        embeddable=False,
    )
    hex_color: Optional[str] = AirweaveField(
        None, description="Calendar color in hex format (e.g., #FF0000).", embeddable=False
    )
    change_key: Optional[str] = AirweaveField(
        None,
        description="Version identifier that changes when the calendar is modified.",
        embeddable=False,
    )
    can_edit: bool = AirweaveField(
        False, description="Whether the user can write to the calendar.", embeddable=False
    )
    can_share: bool = AirweaveField(
        False, description="Whether the user can share the calendar.", embeddable=False
    )
    can_view_private_items: bool = AirweaveField(
        False,
        description="Whether the user can view private events in the calendar.",
        embeddable=False,
    )
    is_default_calendar: bool = AirweaveField(
        False, description="Whether this is the default calendar for new events.", embeddable=False
    )
    is_removable: bool = AirweaveField(
        True, description="Whether this calendar can be deleted from the mailbox.", embeddable=False
    )
    is_tallying_responses: bool = AirweaveField(
        False,
        description="Whether this calendar supports tracking meeting responses.",
        embeddable=False,
    )
    owner: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Information about the calendar owner (name and email).", embeddable=True
    )
    allowed_online_meeting_providers: List[str] = AirweaveField(
        default_factory=list,
        description="Online meeting providers that can be used (teamsForBusiness, etc.).",
        embeddable=False,
    )
    default_online_meeting_provider: Optional[str] = AirweaveField(
        None, description="Default online meeting provider for this calendar.", embeddable=False
    )


class OutlookCalendarEventEntity(BaseEntity):
    """Schema for an Outlook Calendar Event object.

    Reference:
        https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the event ID)
    # - breadcrumbs (calendar breadcrumb)
    # - name (from subject)
    # - created_at (from createdDateTime timestamp)
    # - updated_at (from lastModifiedDateTime timestamp)

    # API fields
    subject: Optional[str] = AirweaveField(
        None, description="The subject/title of the event.", embeddable=True
    )
    body_preview: Optional[str] = AirweaveField(
        None, description="Preview of the event body content.", embeddable=True
    )
    body_content: Optional[str] = AirweaveField(
        None, description="Full body content of the event.", embeddable=True
    )
    body_content_type: Optional[str] = AirweaveField(
        None, description="Content type of the body (html or text).", embeddable=False
    )
    start_datetime: Optional[Any] = AirweaveField(
        None, description="Start date and time of the event.", embeddable=True
    )
    start_timezone: Optional[str] = AirweaveField(
        None, description="Timezone for the start time.", embeddable=False
    )
    end_datetime: Optional[Any] = AirweaveField(
        None, description="End date and time of the event.", embeddable=True
    )
    end_timezone: Optional[str] = AirweaveField(
        None, description="Timezone for the end time.", embeddable=False
    )
    is_all_day: bool = AirweaveField(
        False, description="Whether the event lasts all day.", embeddable=False
    )
    is_cancelled: bool = AirweaveField(
        False, description="Whether the event has been cancelled.", embeddable=True
    )
    is_draft: bool = AirweaveField(
        False, description="Whether the event is a draft.", embeddable=False
    )
    is_online_meeting: bool = AirweaveField(
        False, description="Whether this is an online meeting.", embeddable=True
    )
    is_organizer: bool = AirweaveField(
        False, description="Whether the user is the organizer.", embeddable=False
    )
    is_reminder_on: bool = AirweaveField(
        True, description="Whether a reminder is set.", embeddable=False
    )
    show_as: Optional[str] = AirweaveField(
        None, description="How to show time (free, busy, tentative, oof, etc.).", embeddable=False
    )
    importance: Optional[str] = AirweaveField(
        None, description="Importance level (low, normal, high).", embeddable=True
    )
    sensitivity: Optional[str] = AirweaveField(
        None,
        description="Sensitivity level (normal, personal, private, confidential).",
        embeddable=False,
    )
    response_status: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Response status of the user to the event.", embeddable=False
    )
    organizer: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Event organizer information (name and email).", embeddable=True
    )
    attendees: Optional[List[Dict[str, Any]]] = AirweaveField(
        None, description="List of event attendees with their response status.", embeddable=True
    )
    location: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Primary location information for the event.", embeddable=True
    )
    locations: List[Dict[str, Any]] = AirweaveField(
        default_factory=list,
        description="List of all locations associated with the event.",
        embeddable=True,
    )
    categories: List[str] = AirweaveField(
        default_factory=list, description="Categories assigned to the event.", embeddable=True
    )
    web_link: Optional[str] = AirweaveField(
        None, description="URL to open the event in Outlook on the web.", embeddable=False
    )
    online_meeting_url: Optional[str] = AirweaveField(
        None, description="URL to join the online meeting.", embeddable=True
    )
    online_meeting_provider: Optional[str] = AirweaveField(
        None, description="Online meeting provider (teamsForBusiness, etc.).", embeddable=False
    )
    online_meeting: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Online meeting details and join information.", embeddable=True
    )
    series_master_id: Optional[str] = AirweaveField(
        None,
        description="ID of the master event if this is part of a recurring series.",
        embeddable=False,
    )
    recurrence: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Recurrence pattern for recurring events.", embeddable=True
    )
    reminder_minutes_before_start: Optional[int] = AirweaveField(
        None, description="Minutes before start time when reminder fires.", embeddable=False
    )
    has_attachments: bool = AirweaveField(
        False, description="Whether the event has attachments.", embeddable=False
    )
    ical_uid: Optional[str] = AirweaveField(
        None, description="Unique identifier across calendars.", embeddable=False
    )
    change_key: Optional[str] = AirweaveField(
        None,
        description="Version identifier that changes when event is modified.",
        embeddable=False,
    )
    original_start_timezone: Optional[str] = AirweaveField(
        None, description="Start timezone when event was originally created.", embeddable=False
    )
    original_end_timezone: Optional[str] = AirweaveField(
        None, description="End timezone when event was originally created.", embeddable=False
    )
    allow_new_time_proposals: bool = AirweaveField(
        True, description="Whether invitees can propose new meeting times.", embeddable=False
    )
    hide_attendees: bool = AirweaveField(
        False, description="Whether attendees are hidden from each other.", embeddable=False
    )


class OutlookCalendarAttachmentEntity(FileEntity):
    """Schema for Outlook Calendar Event attachments.

    Represents files attached to calendar events.

    Reference:
        https://learn.microsoft.com/en-us/graph/api/resources/attachment?view=graph-rest-1.0
    """

    # Base fields are inherited from BaseEntity:
    # - entity_id (event_id_attachment_attachment_id)
    # - breadcrumbs (calendar and event breadcrumbs)
    # - name (from attachment name)
    # - created_at (None - attachments don't have creation timestamp)
    # - updated_at (None - attachments don't have update timestamp)

    # File fields are inherited from FileEntity:
    # - url (dummy URL for Graph attachments)
    # - size (attachment size in bytes)
    # - file_type (determined from mime_type)
    # - mime_type (from content_type)
    # - local_path (set after saving bytes)

    # API fields (Outlook Calendar-specific)
    event_id: str = AirweaveField(
        ..., description="ID of the event this attachment belongs to", embeddable=False
    )
    attachment_id: str = AirweaveField(
        ..., description="Microsoft Graph attachment ID", embeddable=False
    )
    content_type: Optional[str] = AirweaveField(
        None, description="MIME type of the attachment", embeddable=False
    )
    is_inline: bool = AirweaveField(
        False, description="Whether the attachment is inline", embeddable=False
    )
    content_id: Optional[str] = AirweaveField(
        None, description="Content ID for inline attachments", embeddable=False
    )
    last_modified_at: Optional[str] = AirweaveField(
        None, description="When the attachment was last modified", embeddable=False
    )
