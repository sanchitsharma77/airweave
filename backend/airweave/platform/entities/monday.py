"""Monday entity schemas.

Based on the Monday.com API (GraphQL-based), we define entity schemas for
commonly used Monday resources: Boards, Groups, Columns, Items, Subitems, and Updates.
"""

from typing import Dict, List, Optional

from airweave.platform.entities._airweave_field import AirweaveField
from airweave.platform.entities._base import BaseEntity


class MondayBoardEntity(BaseEntity):
    """Schema for Monday Board objects.

    Reference:
        https://developer.monday.com/api-reference/reference/boards
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the board ID)
    # - breadcrumbs (empty - boards are top-level)
    # - name (from board name)
    # - created_at (None - boards don't have creation timestamp in API)
    # - updated_at (from updated_at timestamp)

    # API fields
    board_kind: Optional[str] = AirweaveField(
        None,
        description="The board's kind/type: 'public', 'private', or 'share'.",
        embeddable=False,
    )
    columns: List[Dict] = AirweaveField(
        default_factory=list,
        description="A list of columns on the board (each column is typically a dict of fields).",
        embeddable=False,
    )
    description: Optional[str] = AirweaveField(
        None, description="The description of the board.", embeddable=True
    )
    groups: List[Dict] = AirweaveField(
        default_factory=list,
        description="A list of groups on the board (each group is typically a dict of fields).",
        embeddable=False,
    )
    owners: List[Dict] = AirweaveField(
        default_factory=list,
        description="A list of users or teams who own the board.",
        embeddable=True,
    )
    state: Optional[str] = AirweaveField(
        None,
        description="The board's current state: 'active', 'archived', or 'deleted'.",
        embeddable=False,
    )
    workspace_id: Optional[str] = AirweaveField(
        None,
        description="The unique identifier of the workspace containing this board (if any).",
        embeddable=False,
    )


class MondayGroupEntity(BaseEntity):
    """Schema for Monday Group objects.

    Groups are collections of items (rows) within a board.

    Reference:
        https://developer.monday.com/api-reference/reference/boards
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (board_id-group_id composite)
    # - breadcrumbs (board breadcrumb)
    # - name (from group title)
    # - created_at (None - groups don't have creation timestamp)
    # - updated_at (None - groups don't have update timestamp)

    # API fields
    group_id: str = AirweaveField(
        ..., description="The unique identifier (ID) of the group.", embeddable=False
    )
    board_id: str = AirweaveField(
        ..., description="ID of the board this group belongs to.", embeddable=False
    )
    title: Optional[str] = AirweaveField(
        None, description="Title or display name of the group.", embeddable=True
    )
    color: Optional[str] = AirweaveField(
        None, description="Group color code (e.g., 'red', 'green', 'blue', etc.).", embeddable=False
    )
    archived: bool = AirweaveField(
        False, description="Whether this group is archived.", embeddable=False
    )
    items: List[Dict] = AirweaveField(
        default_factory=list,
        description="List of items (rows) contained within this group.",
        embeddable=False,
    )


class MondayColumnEntity(BaseEntity):
    """Schema for Monday Column objects.

    Columns define the structure of data on a Monday board.

    Reference:
        https://developer.monday.com/api-reference/reference/column-types-reference
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (board_id-column_id composite)
    # - breadcrumbs (board breadcrumb)
    # - name (from column title)
    # - created_at (None - columns don't have creation timestamp)
    # - updated_at (None - columns don't have update timestamp)

    # API fields
    column_id: str = AirweaveField(
        ..., description="The unique identifier (ID) of the column.", embeddable=False
    )
    board_id: str = AirweaveField(
        ..., description="ID of the board this column belongs to.", embeddable=False
    )
    title: Optional[str] = AirweaveField(
        None, description="The display title of the column.", embeddable=True
    )
    column_type: Optional[str] = AirweaveField(
        None,
        description="The type of the column (e.g., 'text', 'number', 'date', 'link').",
        embeddable=True,
    )
    description: Optional[str] = AirweaveField(
        None, description="The description of the column.", embeddable=True
    )
    settings_str: Optional[str] = AirweaveField(
        None,
        description="Raw settings/configuration details for the column.",
        embeddable=False,
    )
    archived: bool = AirweaveField(
        False, description="Whether this column is archived or hidden.", embeddable=False
    )


class MondayItemEntity(BaseEntity):
    """Schema for Monday Item objects (rows on a board).

    Reference:
        https://developer.monday.com/api-reference/reference/boards
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the item ID)
    # - breadcrumbs (board breadcrumb)
    # - name (from item name)
    # - created_at (from created_at timestamp)
    # - updated_at (from updated_at timestamp)

    # API fields
    item_id: str = AirweaveField(
        ..., description="The unique identifier (ID) of the item.", embeddable=False
    )
    board_id: str = AirweaveField(
        ..., description="ID of the board this item belongs to.", embeddable=False
    )
    group_id: Optional[str] = AirweaveField(
        None, description="ID of the group this item is placed in.", embeddable=False
    )
    state: Optional[str] = AirweaveField(
        None,
        description="The current state of the item: active, archived, or deleted.",
        embeddable=False,
    )
    column_values: List[Dict] = AirweaveField(
        default_factory=list,
        description="A list of column-value dicts that contain the data for each column.",
        embeddable=True,
    )
    creator: Optional[Dict] = AirweaveField(
        None, description="Information about the user/team who created this item.", embeddable=True
    )


class MondaySubitemEntity(BaseEntity):
    """Schema for Monday Subitem objects.

    Subitems are items nested under a parent item, often in a dedicated 'Subitems' column.

    Reference:
        https://developer.monday.com/api-reference/reference/boards
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the subitem ID)
    # - breadcrumbs (board and item breadcrumbs)
    # - name (from subitem name)
    # - created_at (from created_at timestamp)
    # - updated_at (from updated_at timestamp)

    # API fields
    subitem_id: str = AirweaveField(
        ..., description="The unique identifier (ID) of the subitem.", embeddable=False
    )
    parent_item_id: str = AirweaveField(
        ..., description="ID of the parent item this subitem belongs to.", embeddable=False
    )
    board_id: str = AirweaveField(
        ..., description="ID of the board that this subitem resides in.", embeddable=False
    )
    group_id: Optional[str] = AirweaveField(
        None, description="ID of the group this subitem is placed in.", embeddable=False
    )
    state: Optional[str] = AirweaveField(
        None,
        description="The current state of the subitem: active, archived, or deleted.",
        embeddable=False,
    )
    column_values: List[Dict] = AirweaveField(
        default_factory=list,
        description="A list of column-value dicts for each column on the subitem.",
        embeddable=True,
    )
    creator: Optional[Dict] = AirweaveField(
        None,
        description="Information about the user/team who created this subitem.",
        embeddable=True,
    )


class MondayUpdateEntity(BaseEntity):
    """Schema for Monday Update objects.

    monday.com updates add notes and discussions to items outside of their column data.

    Reference:
        https://developer.monday.com/api-reference/reference/updates
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the update ID)
    # - breadcrumbs (board and optionally item breadcrumbs)
    # - name (from body preview)
    # - created_at (from created_at timestamp)
    # - updated_at (None - updates don't have update timestamp)

    # API fields
    update_id: str = AirweaveField(
        ..., description="The unique identifier (ID) of the update.", embeddable=False
    )
    item_id: Optional[str] = AirweaveField(
        None,
        description=(
            "ID of the item this update is referencing (could also be a board-level update)."
        ),
        embeddable=False,
    )
    board_id: Optional[str] = AirweaveField(
        None, description="ID of the board, if applicable.", embeddable=False
    )
    creator_id: Optional[str] = AirweaveField(
        None,
        description="ID of the user who created this update.",
        embeddable=False,
    )
    body: Optional[str] = AirweaveField(
        None,
        description="The text (body) of the update, which may include markdown or HTML formatting.",
        embeddable=True,
    )
    assets: List[Dict] = AirweaveField(
        default_factory=list,
        description="Assets (e.g. images, attachments) associated with this update.",
        embeddable=False,
    )
