"""Entity-specific action types for entity sync pipeline.

Extends generic action types with entity-specific fields like
entity_definition_id, db_id, chunk_entities, and existing_map.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple
from uuid import UUID

from airweave.platform.sync.actions.types import (
    ActionBatch,
    DeleteAction,
    InsertAction,
    KeepAction,
    UpdateAction,
)

if TYPE_CHECKING:
    from airweave import models
    from airweave.platform.entities._base import BaseEntity


# =============================================================================
# Entity Action Types (extend generic with entity-specific fields)
# =============================================================================


@dataclass
class EntityInsertAction(InsertAction["BaseEntity"]):
    """Entity should be inserted (new entity, not in database).

    Extends InsertAction with entity-specific fields.
    """

    entity_definition_id: UUID = field(default=None)
    chunk_entities: List["BaseEntity"] = field(default_factory=list)

    @property
    def entity(self) -> "BaseEntity":
        """Get the entity (alias for payload)."""
        return self.payload

    @property
    def entity_id(self) -> str:
        """Get the entity ID."""
        return self.payload.entity_id

    @property
    def entity_type(self) -> str:
        """Get the entity type name."""
        return self.payload.__class__.__name__


@dataclass
class EntityUpdateAction(UpdateAction["BaseEntity"]):
    """Entity should be updated (hash changed from stored value).

    Extends UpdateAction with entity-specific fields.
    """

    entity_definition_id: UUID = field(default=None)
    db_id: UUID = field(default=None)  # Existing database record ID
    chunk_entities: List["BaseEntity"] = field(default_factory=list)

    @property
    def entity(self) -> "BaseEntity":
        """Get the entity (alias for payload)."""
        return self.payload

    @property
    def entity_id(self) -> str:
        """Get the entity ID."""
        return self.payload.entity_id

    @property
    def entity_type(self) -> str:
        """Get the entity type name."""
        return self.payload.__class__.__name__


@dataclass
class EntityDeleteAction(DeleteAction["BaseEntity"]):
    """Entity should be deleted (DeletionEntity from source).

    Extends DeleteAction with entity-specific fields.
    """

    entity_definition_id: UUID = field(default=None)
    db_id: Optional[UUID] = None  # May not exist in DB if never synced

    @property
    def entity(self) -> "BaseEntity":
        """Get the entity (alias for payload)."""
        return self.payload

    @property
    def entity_id(self) -> str:
        """Get the entity ID."""
        return self.payload.entity_id

    @property
    def entity_type(self) -> str:
        """Get the entity type name."""
        return self.payload.__class__.__name__


@dataclass
class EntityKeepAction(KeepAction["BaseEntity"]):
    """Entity is unchanged (hash matches stored value).

    Extends KeepAction with entity-specific fields.
    """

    entity_definition_id: UUID = field(default=None)

    @property
    def entity(self) -> "BaseEntity":
        """Get the entity (alias for payload)."""
        return self.payload

    @property
    def entity_id(self) -> str:
        """Get the entity ID."""
        return self.payload.entity_id

    @property
    def entity_type(self) -> str:
        """Get the entity type name."""
        return self.payload.__class__.__name__


# =============================================================================
# Entity Action Batch (extends generic with existing_map)
# =============================================================================


@dataclass
class EntityActionBatch(ActionBatch["BaseEntity"]):
    """Container for a batch of resolved entity actions.

    Extends ActionBatch with entity-specific existing_map for updates/deletes.
    Uses entity-specific action types in the lists.
    """

    # Override with entity-specific types
    inserts: List[EntityInsertAction] = field(default_factory=list)
    updates: List[EntityUpdateAction] = field(default_factory=list)
    deletes: List[EntityDeleteAction] = field(default_factory=list)
    keeps: List[EntityKeepAction] = field(default_factory=list)

    # Entity-specific: map of (entity_id, entity_definition_id) -> DB entity
    existing_map: Dict[Tuple[str, UUID], "models.Entity"] = field(default_factory=dict)

    def get_entities_to_process(self) -> List["BaseEntity"]:
        """Get entities that need content processing (INSERT + UPDATE)."""
        entities = []
        for action in self.inserts:
            entities.append(action.entity)
        for action in self.updates:
            entities.append(action.entity)
        return entities
