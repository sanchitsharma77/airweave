"""Actions module for sync pipelines.

Organized by domain:
- entity/: Entity action types, resolver, dispatcher, builder
- access_control/: Access control membership action types, resolver, dispatcher

Each domain has its own types, resolver, and dispatcher tailored to its needs.
"""

# Entity actions
# Access control actions
from airweave.platform.sync.actions.access_control import (
    ACActionBatch,
    ACActionDispatcher,
    ACActionResolver,
    ACDeleteAction,
    ACInsertAction,
    ACKeepAction,
    ACUpdateAction,
    ACUpsertAction,
)
from airweave.platform.sync.actions.entity import (
    EntityActionBatch,
    EntityActionDispatcher,
    EntityActionResolver,
    EntityDeleteAction,
    EntityDispatcherBuilder,
    EntityInsertAction,
    EntityKeepAction,
    EntityUpdateAction,
)

__all__ = [
    # Entity types
    "EntityActionBatch",
    "EntityDeleteAction",
    "EntityInsertAction",
    "EntityKeepAction",
    "EntityUpdateAction",
    # Entity resolver and dispatcher
    "EntityActionResolver",
    "EntityActionDispatcher",
    "EntityDispatcherBuilder",
    # AC types
    "ACActionBatch",
    "ACDeleteAction",
    "ACInsertAction",
    "ACKeepAction",
    "ACUpdateAction",
    "ACUpsertAction",
    # AC resolver and dispatcher
    "ACActionResolver",
    "ACActionDispatcher",
]
