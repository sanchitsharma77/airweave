"""Action dataclasses for entity pipeline.

Actions are first-class citizens representing the operation to perform on an entity.
Each action type contains the entity and metadata needed for handlers to execute.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple
from uuid import UUID

if TYPE_CHECKING:
    from airweave import models
    from airweave.platform.entities._base import BaseEntity


@dataclass
class BaseAction:
    """Base class for all entity actions."""

    entity: "BaseEntity"
    entity_definition_id: UUID

    @property
    def entity_id(self) -> str:
        """Get the entity ID."""
        return self.entity.entity_id

    @property
    def entity_type(self) -> str:
        """Get the entity type name."""
        return self.entity.__class__.__name__


@dataclass
class InsertAction(BaseAction):
    """Entity should be inserted (new entity, not in database)."""

    chunk_entities: List["BaseEntity"] = field(default_factory=list)


@dataclass
class UpdateAction(BaseAction):
    """Entity should be updated (hash changed from stored value)."""

    db_id: UUID = field(default=None)  # Existing database record ID
    chunk_entities: List["BaseEntity"] = field(default_factory=list)


@dataclass
class DeleteAction(BaseAction):
    """Entity should be deleted (DeletionEntity from source)."""

    db_id: Optional[UUID] = None  # May not exist in DB if never synced


@dataclass
class KeepAction(BaseAction):
    """Entity is unchanged (hash matches stored value)."""

    pass


@dataclass
class ActionBatch:
    """Container for a batch of resolved actions.

    Provides convenient access to actions grouped by type and utility methods
    for checking batch state.
    """

    inserts: List[InsertAction] = field(default_factory=list)
    updates: List[UpdateAction] = field(default_factory=list)
    deletes: List[DeleteAction] = field(default_factory=list)
    keeps: List[KeepAction] = field(default_factory=list)

    # Map of (entity_id, entity_definition_id) -> DB entity for updates/deletes
    existing_map: Dict[Tuple[str, UUID], "models.Entity"] = field(default_factory=dict)

    @property
    def has_mutations(self) -> bool:
        """Check if batch has any INSERT/UPDATE/DELETE actions."""
        return bool(self.inserts or self.updates or self.deletes)

    @property
    def mutation_count(self) -> int:
        """Get total count of mutation actions."""
        return len(self.inserts) + len(self.updates) + len(self.deletes)

    @property
    def total_count(self) -> int:
        """Get total count of all actions including KEEP."""
        return self.mutation_count + len(self.keeps)

    def get_entities_to_process(self) -> List["BaseEntity"]:
        """Get entities that need content processing (INSERT + UPDATE)."""
        entities = []
        for action in self.inserts:
            entities.append(action.entity)
        for action in self.updates:
            entities.append(action.entity)
        return entities

    def summary(self) -> str:
        """Get a summary string of the batch."""
        return (
            f"{len(self.inserts)} inserts, {len(self.updates)} updates, "
            f"{len(self.deletes)} deletes, {len(self.keeps)} keeps"
        )
