"""Generic action types for sync pipelines.

Base action types using generics. Domain-specific actions (entity, AC)
extend these with additional fields as needed.

Type Hierarchy:
    BaseAction[T]
    ├── InsertAction[T]
    ├── UpdateAction[T]
    ├── DeleteAction[T]
    ├── KeepAction[T]
    └── UpsertAction[T]

    ActionBatch[T] - container for batches of actions
"""

from dataclasses import dataclass, field
from typing import Generic, List, TypeVar

# Generic payload type
T = TypeVar("T")


# =============================================================================
# Base Action Types (Generic)
# =============================================================================


@dataclass
class BaseAction(Generic[T]):
    """Base class for all actions."""

    payload: T


@dataclass
class InsertAction(BaseAction[T]):
    """Item should be inserted (new, not in database)."""

    pass


@dataclass
class UpdateAction(BaseAction[T]):
    """Item should be updated (changed from stored value)."""

    pass


@dataclass
class DeleteAction(BaseAction[T]):
    """Item should be deleted."""

    pass


@dataclass
class KeepAction(BaseAction[T]):
    """Item is unchanged (no action needed)."""

    pass


@dataclass
class UpsertAction(BaseAction[T]):
    """Item should be upserted (insert or update on conflict)."""

    pass


# =============================================================================
# Action Batch (Generic)
# =============================================================================


@dataclass
class ActionBatch(Generic[T]):
    """Container for a batch of resolved actions.

    Generic over the payload type T. Supports all action types for flexibility.
    """

    inserts: List[InsertAction[T]] = field(default_factory=list)
    updates: List[UpdateAction[T]] = field(default_factory=list)
    deletes: List[DeleteAction[T]] = field(default_factory=list)
    keeps: List[KeepAction[T]] = field(default_factory=list)
    upserts: List[UpsertAction[T]] = field(default_factory=list)

    @property
    def has_mutations(self) -> bool:
        """Check if batch has any mutation actions."""
        return bool(self.inserts or self.updates or self.deletes or self.upserts)

    @property
    def mutation_count(self) -> int:
        """Get total count of mutation actions."""
        return len(self.inserts) + len(self.updates) + len(self.deletes) + len(self.upserts)

    @property
    def total_count(self) -> int:
        """Get total count of all actions including KEEP."""
        return self.mutation_count + len(self.keeps)

    def summary(self) -> str:
        """Get a summary string of the batch."""
        parts = []
        if self.inserts:
            parts.append(f"{len(self.inserts)} inserts")
        if self.updates:
            parts.append(f"{len(self.updates)} updates")
        if self.deletes:
            parts.append(f"{len(self.deletes)} deletes")
        if self.upserts:
            parts.append(f"{len(self.upserts)} upserts")
        if self.keeps:
            parts.append(f"{len(self.keeps)} keeps")
        return ", ".join(parts) if parts else "empty"

    def get_payloads(self) -> List[T]:
        """Get all payloads that need processing (from inserts + updates + upserts)."""
        payloads = []
        for action in self.inserts:
            payloads.append(action.payload)
        for action in self.updates:
            payloads.append(action.payload)
        for action in self.upserts:
            payloads.append(action.payload)
        return payloads
