"""Trello entity schemas."""

from typing import Any, Dict, List, Optional

from airweave.platform.entities._airweave_field import AirweaveField
from airweave.platform.entities._base import BaseEntity


class TrelloBoardEntity(BaseEntity):
    """Schema for Trello board entities.

    Reference:
        https://developer.atlassian.com/cloud/trello/rest/api-group-boards/
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the Trello board ID)
    # - breadcrumbs (empty - boards are top-level)
    # - name (from board name)
    # - created_at (None - boards don't have creation timestamp)
    # - updated_at (None - boards don't have update timestamp)

    # API fields
    trello_id: str = AirweaveField(
        ..., description="Trello's unique identifier for the board", embeddable=False
    )
    desc: Optional[str] = AirweaveField(
        None, description="Description of the board", embeddable=True
    )
    closed: bool = AirweaveField(
        False, description="Whether the board is closed/archived", embeddable=False
    )
    url: Optional[str] = AirweaveField(None, description="URL to the board", embeddable=False)
    short_url: Optional[str] = AirweaveField(
        None, description="Short URL to the board", embeddable=False
    )
    prefs: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Board preferences and settings", embeddable=False
    )
    id_organization: Optional[str] = AirweaveField(
        None, description="ID of the organization this board belongs to", embeddable=False
    )
    pinned: bool = AirweaveField(False, description="Whether the board is pinned", embeddable=False)


class TrelloListEntity(BaseEntity):
    """Schema for Trello list entities (columns on a board).

    Reference:
        https://developer.atlassian.com/cloud/trello/rest/api-group-lists/
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the Trello list ID)
    # - breadcrumbs (board breadcrumb)
    # - name (from list name)
    # - created_at (None - lists don't have creation timestamp)
    # - updated_at (None - lists don't have update timestamp)

    # API fields
    trello_id: str = AirweaveField(
        ..., description="Trello's unique identifier for the list", embeddable=False
    )
    id_board: str = AirweaveField(
        ..., description="ID of the board this list belongs to", embeddable=False
    )
    board_name: str = AirweaveField(
        ..., description="Name of the board this list belongs to", embeddable=True
    )
    closed: bool = AirweaveField(
        False, description="Whether the list is archived", embeddable=False
    )
    pos: Optional[float] = AirweaveField(
        None, description="Position of the list on the board", embeddable=False
    )
    subscribed: Optional[bool] = AirweaveField(
        None, description="Whether the user is subscribed to this list", embeddable=False
    )


class TrelloCardEntity(BaseEntity):
    """Schema for Trello card entities.

    Reference:
        https://developer.atlassian.com/cloud/trello/rest/api-group-cards/
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the Trello card ID)
    # - breadcrumbs (board and list breadcrumbs)
    # - name (from card name)
    # - created_at (None - cards don't have creation timestamp)
    # - updated_at (from date_last_activity)

    # API fields
    trello_id: str = AirweaveField(
        ..., description="Trello's unique identifier for the card", embeddable=False
    )
    desc: Optional[str] = AirweaveField(
        None, description="Description/notes on the card", embeddable=True
    )
    id_board: str = AirweaveField(
        ..., description="ID of the board this card belongs to", embeddable=False
    )
    board_name: str = AirweaveField(..., description="Name of the board", embeddable=True)
    id_list: str = AirweaveField(
        ..., description="ID of the list this card belongs to", embeddable=False
    )
    list_name: str = AirweaveField(..., description="Name of the list", embeddable=True)
    closed: bool = AirweaveField(False, description="Whether the card is archived", embeddable=True)
    due: Optional[str] = AirweaveField(None, description="Due date for the card", embeddable=True)
    due_complete: Optional[bool] = AirweaveField(
        None, description="Whether the due date is marked complete", embeddable=True
    )
    date_last_activity: Optional[Any] = AirweaveField(
        None,
        description="Last activity date on the card",
        embeddable=False,
    )
    id_members: List[str] = AirweaveField(
        default_factory=list,
        description="List of member IDs assigned to this card",
        embeddable=False,
    )
    members: List[Dict[str, Any]] = AirweaveField(
        default_factory=list, description="Members assigned to this card", embeddable=True
    )
    id_labels: List[str] = AirweaveField(
        default_factory=list,
        description="List of label IDs attached to this card",
        embeddable=False,
    )
    labels: List[Dict[str, Any]] = AirweaveField(
        default_factory=list, description="Labels attached to this card", embeddable=True
    )
    id_checklists: List[str] = AirweaveField(
        default_factory=list, description="List of checklist IDs on this card", embeddable=False
    )
    badges: Optional[Dict[str, Any]] = AirweaveField(
        None,
        description="Badge information (comments, attachments, votes, etc.)",
        embeddable=True,
    )
    pos: Optional[float] = AirweaveField(
        None, description="Position of the card in the list", embeddable=False
    )
    short_link: Optional[str] = AirweaveField(
        None, description="Short link to the card", embeddable=False
    )
    short_url: Optional[str] = AirweaveField(
        None, description="Short URL to the card", embeddable=False
    )
    url: Optional[str] = AirweaveField(None, description="Full URL to the card", embeddable=False)
    start: Optional[str] = AirweaveField(
        None, description="Start date for the card", embeddable=True
    )
    subscribed: Optional[bool] = AirweaveField(
        None, description="Whether the user is subscribed to this card", embeddable=False
    )


class TrelloChecklistEntity(BaseEntity):
    """Schema for Trello checklist entities.

    Reference:
        https://developer.atlassian.com/cloud/trello/rest/api-group-checklists/
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the Trello checklist ID)
    # - breadcrumbs (board, list, and card breadcrumbs)
    # - name (from checklist name)
    # - created_at (None - checklists don't have creation timestamp)
    # - updated_at (None - checklists don't have update timestamp)

    # API fields
    trello_id: str = AirweaveField(
        ..., description="Trello's unique identifier for the checklist", embeddable=False
    )
    id_board: str = AirweaveField(
        ..., description="ID of the board this checklist belongs to", embeddable=False
    )
    id_card: str = AirweaveField(
        ..., description="ID of the card this checklist belongs to", embeddable=False
    )
    card_name: str = AirweaveField(..., description="Name of the card", embeddable=True)
    pos: Optional[float] = AirweaveField(
        None, description="Position of the checklist on the card", embeddable=False
    )
    check_items: List[Dict[str, Any]] = AirweaveField(
        default_factory=list,
        description="List of checklist items with their states",
        embeddable=True,
    )


class TrelloMemberEntity(BaseEntity):
    """Schema for Trello member (user) entities.

    Reference:
        https://developer.atlassian.com/cloud/trello/rest/api-group-members/
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the Trello member ID)
    # - breadcrumbs (empty - members are top-level)
    # - name (from full_name or username)
    # - created_at (None - members don't have creation timestamp)
    # - updated_at (None - members don't have update timestamp)

    # API fields
    username: str = AirweaveField(..., description="The username of the member", embeddable=True)
    trello_id: str = AirweaveField(
        ..., description="Trello's unique identifier for the member", embeddable=False
    )
    full_name: Optional[str] = AirweaveField(
        None, description="Full name of the member", embeddable=True
    )
    initials: Optional[str] = AirweaveField(None, description="Member's initials", embeddable=False)
    avatar_url: Optional[str] = AirweaveField(
        None, description="URL to the member's avatar", embeddable=False
    )
    bio: Optional[str] = AirweaveField(None, description="Member's bio", embeddable=True)
    url: Optional[str] = AirweaveField(
        None, description="URL to the member's profile", embeddable=False
    )
    id_boards: List[str] = AirweaveField(
        default_factory=list,
        description="List of board IDs the member belongs to",
        embeddable=False,
    )
    member_type: Optional[str] = AirweaveField(
        None, description="Type of member (normal, admin, etc.)", embeddable=False
    )
