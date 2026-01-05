"""Access control action types for membership sync pipeline.

Extends generic action types with AC-specific convenience properties.
Simpler than entity types - no extra fields needed.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List

from airweave.platform.sync.actions.types import (
    ActionBatch,
    DeleteAction,
    InsertAction,
    KeepAction,
    UpdateAction,
    UpsertAction,
)

if TYPE_CHECKING:
    from airweave.platform.access_control.schemas import MembershipTuple


# =============================================================================
# AC Action Types (extend generic with convenience properties)
# =============================================================================


@dataclass
class ACInsertAction(InsertAction["MembershipTuple"]):
    """Membership should be inserted (new membership, not in database).

    Future: Used when we add hash comparison to detect new memberships.
    """

    @property
    def membership(self) -> "MembershipTuple":
        """Get the membership (alias for payload)."""
        return self.payload

    @property
    def member_id(self) -> str:
        """Get the member ID."""
        return self.payload.member_id

    @property
    def group_id(self) -> str:
        """Get the group ID."""
        return self.payload.group_id


@dataclass
class ACUpdateAction(UpdateAction["MembershipTuple"]):
    """Membership should be updated (metadata changed from stored value).

    Future: Used when we add hash comparison to detect changed memberships.
    """

    @property
    def membership(self) -> "MembershipTuple":
        """Get the membership (alias for payload)."""
        return self.payload

    @property
    def member_id(self) -> str:
        """Get the member ID."""
        return self.payload.member_id

    @property
    def group_id(self) -> str:
        """Get the group ID."""
        return self.payload.group_id


@dataclass
class ACDeleteAction(DeleteAction["MembershipTuple"]):
    """Membership should be deleted (stale membership to remove).

    Future: Used when we add stale membership cleanup.
    """

    @property
    def membership(self) -> "MembershipTuple":
        """Get the membership (alias for payload)."""
        return self.payload

    @property
    def member_id(self) -> str:
        """Get the member ID."""
        return self.payload.member_id

    @property
    def group_id(self) -> str:
        """Get the group ID."""
        return self.payload.group_id


@dataclass
class ACKeepAction(KeepAction["MembershipTuple"]):
    """Membership is unchanged (hash matches stored value).

    Future: Used when we add hash comparison to skip unchanged memberships.
    """

    @property
    def membership(self) -> "MembershipTuple":
        """Get the membership (alias for payload)."""
        return self.payload

    @property
    def member_id(self) -> str:
        """Get the member ID."""
        return self.payload.member_id

    @property
    def group_id(self) -> str:
        """Get the group ID."""
        return self.payload.group_id


@dataclass
class ACUpsertAction(UpsertAction["MembershipTuple"]):
    """Membership should be upserted (insert or update on conflict).

    Currently ALL memberships use this action type (no hash comparison).
    This is the default action until we implement more sophisticated
    change detection.
    """

    @property
    def membership(self) -> "MembershipTuple":
        """Get the membership (alias for payload)."""
        return self.payload

    @property
    def member_id(self) -> str:
        """Get the member ID."""
        return self.payload.member_id

    @property
    def group_id(self) -> str:
        """Get the group ID."""
        return self.payload.group_id


# =============================================================================
# AC Action Batch (extends generic)
# =============================================================================


@dataclass
class ACActionBatch(ActionBatch["MembershipTuple"]):
    """Container for a batch of resolved access control membership actions.

    Extends ActionBatch with AC-specific action types.
    """

    # Override with AC-specific types
    inserts: List[ACInsertAction] = field(default_factory=list)
    updates: List[ACUpdateAction] = field(default_factory=list)
    deletes: List[ACDeleteAction] = field(default_factory=list)
    keeps: List[ACKeepAction] = field(default_factory=list)
    upserts: List[ACUpsertAction] = field(default_factory=list)

    def get_memberships(self) -> List["MembershipTuple"]:
        """Get all membership tuples for processing (from upserts)."""
        return [action.membership for action in self.upserts]
