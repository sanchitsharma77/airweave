"""Actions module for sync pipelines.

Generic base types + domain-specific extensions:

Generic Types (types.py):
    BaseAction[T], InsertAction[T], UpdateAction[T], DeleteAction[T],
    KeepAction[T], UpsertAction[T], ActionBatch[T]

Entity Types (entity_types.py):
    EntityInsertAction, EntityUpdateAction, EntityDeleteAction,
    EntityKeepAction, EntityActionBatch

AC Types (access_control_types.py):
    ACInsertAction, ACUpdateAction, ACDeleteAction, ACKeepAction,
    ACUpsertAction, ACActionBatch

Resolvers and Dispatchers:
    EntityActionResolver, EntityActionDispatcher
    ACActionResolver, ACActionDispatcher
"""

# AC-specific types
# Resolvers and dispatchers
from .access_control_dispatcher import ACActionDispatcher
from .access_control_resolver import ACActionResolver
from .access_control_types import (
    ACActionBatch,
    ACDeleteAction,
    ACInsertAction,
    ACKeepAction,
    ACUpdateAction,
    ACUpsertAction,
)
from .entity_dispatcher import EntityActionDispatcher
from .entity_resolver import EntityActionResolver

# Entity-specific types
from .entity_types import (
    EntityActionBatch,
    EntityDeleteAction,
    EntityInsertAction,
    EntityKeepAction,
    EntityUpdateAction,
)

# Generic base types
from .types import (
    ActionBatch,
    BaseAction,
    DeleteAction,
    InsertAction,
    KeepAction,
    UpdateAction,
    UpsertAction,
)

__all__ = [
    # Generic base types
    "ActionBatch",
    "BaseAction",
    "DeleteAction",
    "InsertAction",
    "KeepAction",
    "UpdateAction",
    "UpsertAction",
    # Entity types
    "EntityActionBatch",
    "EntityDeleteAction",
    "EntityInsertAction",
    "EntityKeepAction",
    "EntityUpdateAction",
    # AC types
    "ACActionBatch",
    "ACDeleteAction",
    "ACInsertAction",
    "ACKeepAction",
    "ACUpdateAction",
    "ACUpsertAction",
    # Resolvers and dispatchers
    "ACActionDispatcher",
    "ACActionResolver",
    "EntityActionDispatcher",
    "EntityActionResolver",
]
