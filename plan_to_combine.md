# Plan: Integrate Access Control POC into Vespa Branch

> **Goal**: Bring the access control system from `poc/access-controls-on-data` into `feat/merge-sharepoint-vespa`
> **Complexity**: Medium-High (touches database, sync pipeline, search, and Vespa)
> **Estimated Tasks**: 24 discrete tasks across 6 phases
> **Architecture Decision**: Access control sync uses handler/dispatcher pattern (like entity sync)

---

## Overview

The POC branch implements:
- Entity-level access control (`BaseEntity.access` with `viewers[]` and `is_public`)
- Access control membership sync (user→group, group→group tuples to Postgres)
- Search-time filtering via `AccessBroker` → Qdrant filter

The Vespa branch has:
- New sync architecture (handlers, processors, dispatcher)
- Vespa as a destination (requires YQL filter translation)
- `ProcessingRequirement` system for different destinations

**Key Challenge**: The POC was built on the OLD sync architecture. We need to adapt it to the NEW handler/dispatcher pattern while also adding Vespa support.

---

## Critical Design Decision: Access Control Awareness

### The Problem

Sources like Slack, Asana, Gmail don't have access control. If we naively add access control filtering:

```python
# WRONG - breaks existing sources!
if entity.access:
    fields["access_is_public"] = entity.access.is_public
    fields["access_viewers"] = entity.access.viewers
else:
    # Default: not public, no viewers → entity becomes INVISIBLE!
    fields["access_is_public"] = False
    fields["access_viewers"] = []
```

This would make ALL entities from non-access-control sources invisible at search time.

### The Solution: Source Decorator Flag

Add `supports_access_control` to the `@source` decorator:

```python
# Sources WITHOUT access control (default) - entities visible to everyone
@source(
    name="Slack",
    short_name="slack",
    supports_access_control=False,  # Default, can omit
    ...
)

# Sources WITH access control - entities filtered by permissions
@source(
    name="SharePoint 2019 V2",
    short_name="sharepoint2019v2",
    supports_access_control=True,  # Explicitly enabled
    ...
)
```

### Behavior Matrix

| Source supports AC | Entity has `access` | Sync behavior | Search behavior |
|-------------------|---------------------|---------------|-----------------|
| `False` | N/A | No membership sync, skip access field | No filter applied (visible to all) |
| `True` | `None` | **ERROR** - source bug | N/A |
| `True` | Set | Store access fields | Apply access filter |

### Why This Matters

1. **Existing sources continue working** - No changes needed for Slack, Asana, etc.
2. **Explicit opt-in** - Access control is a conscious choice per source
3. **Validation** - Can warn/error if source declares `supports_access_control=True` but yields entities without `access` field
4. **Search-time efficiency** - Skip AccessBroker queries for non-AC sources

---

## Design Decision: Access Control Sync Architecture

### Question: Use New Handler/Dispatcher Pattern?

The new sync architecture (handlers, processors, dispatcher) was built for **destinations** that need:
- Different processing per destination (chunking, embedding)
- All-or-nothing semantics across multiple destinations
- Content transformation via processors

Access control memberships **today** are simpler:
- **Only go to Postgres** (not to vector DBs)
- **No content transformation** (just tuples)
- **Only upsert** (no UPDATE/DELETE distinction yet)

### Decision: YES - Use Handler/Dispatcher Pattern

After discussion, we **WILL** use the handler/dispatcher pattern for access control memberships because:

1. **Future destinations**: Redis caching for access context is planned
2. **Future actions**: Delete actions for stale memberships, update actions
3. **Consistency**: Same patterns make the codebase easier to maintain
4. **Extensibility**: Easy to add new handlers/actions later

Even though the current implementation is simple (1 handler, 1 action type), the architecture will mirror the entity sync pipeline.

### Naming Convention: Entity vs AC (Implemented)

We use **AC prefix** (not Membership) and **generic types**:

```python
# Generic base types (types.py)
BaseAction[T], InsertAction[T], UpdateAction[T], DeleteAction[T], KeepAction[T], UpsertAction[T]
ActionBatch[T]

# Entity sync (entity_types.py) - extends generics with entity-specific fields
EntityInsertAction(InsertAction[BaseEntity])  # + entity_definition_id, chunk_entities
EntityActionBatch(ActionBatch[BaseEntity])    # + existing_map

# AC sync (access_control_types.py) - extends generics
ACInsertAction(InsertAction[MembershipTuple])
ACUpsertAction(UpsertAction[MembershipTuple])  # Currently used
ACActionBatch(ActionBatch[MembershipTuple])

# Generic protocol (protocol.py)
ActionHandler[T, B]  # Parameterized by payload type T and batch type B
EntityActionHandler = ActionHandler[BaseEntity, EntityActionBatch]  # Type alias
ACActionHandler = ActionHandler[MembershipTuple, ACActionBatch]     # Type alias
```

### Current vs Future Architecture (Implemented)

```
CURRENT (Phase 3 - IMPLEMENTED):
┌───────────────────────────────────────────┐
│  ACActionResolver                          │
│  └── All memberships → ACUpsertAction     │
├───────────────────────────────────────────┤
│  ACActionDispatcher                        │
│  └── 1 handler (Postgres)                 │
├───────────────────────────────────────────┤
│  ACPostgresHandler                         │
│  ├── handle_upserts() → bulk upsert       │
│  └── handle_deletes() → (ready for impl)  │
└───────────────────────────────────────────┘

FUTURE:
┌───────────────────────────────────────────┐
│  ACActionResolver                          │
│  └── Compare hashes → Upsert/Keep/Delete  │
├───────────────────────────────────────────┤
│  ACActionDispatcher                        │
│  └── 2+ handlers (Postgres, Redis)        │
├───────────────────────────────────────────┤
│  ACPostgresHandler                         │
│  ├── handle_upserts() → bulk upsert       │
│  └── handle_deletes() → remove stale      │
│  ACRedisHandler (cache)                    │
│  ├── handle_upserts() → cache principals  │
│  └── handle_deletes() → invalidate cache  │
└───────────────────────────────────────────┘
```

### No Backwards Compatibility

Per user request, we renamed classes directly and updated all imports. No aliases needed.

---

## Phase 1: Database & Models (No Breaking Changes)

These changes can be made first as they don't affect existing functionality.

### Task 1.1: Add AccessControlMembership Model

**Source**: `airweave-access-controls/backend/airweave/models/access_control_membership.py`
**Target**: `airweave-sharepoint-vespa/backend/airweave/models/access_control_membership.py`

```
Action: Copy file directly (no changes needed)
```

The model defines:
- `member_id`, `member_type`, `group_id`, `group_name`
- `source_name`, `source_connection_id` (FK with CASCADE)
- Indexes for member lookup, group lookup, and source cleanup

**Also update**: `backend/airweave/models/__init__.py` to export the new model.

### Task 1.2: Add Database Migration

**Source**: `airweave-access-controls/backend/alembic/versions/24147f35a4a5_add_access_control_membership_table.py`
**Target**: `airweave-sharepoint-vespa/backend/alembic/versions/` (new revision)

```
Action: Create new migration (may need different revision ID if conflicts)
Verify: Foreign key to source_connection with CASCADE delete
```

### Task 1.3: Add AccessControl Field to BaseEntity

**Source**: `airweave-access-controls/backend/airweave/platform/entities/_base.py`
**Target**: `airweave-sharepoint-vespa/backend/airweave/platform/entities/_base.py`

```python
# Add this class (from POC)
class AccessControl(BaseModel):
    """Access control metadata for an entity."""
    viewers: List[str] = Field(default_factory=list)
    is_public: bool = Field(default=False)

# Add field to BaseEntity
class BaseEntity(BaseModel):
    # ... existing fields ...
    access: Optional[AccessControl] = Field(default=None, description="Access control metadata")
```

**Action**: Diff the two files, merge the `AccessControl` class and field addition.

### Task 1.4: Add CRUD for AccessControlMembership

**Source**: `airweave-access-controls/backend/airweave/crud/crud_access_control_membership.py`
**Target**: `airweave-sharepoint-vespa/backend/airweave/crud/crud_access_control_membership.py`

```
Action: Copy file directly
Also update: backend/airweave/crud/__init__.py to export it
```

Key methods:
- `get_by_member()` - for AccessBroker queries
- `get_by_member_and_collection()` - scoped to collection
- `bulk_create()` - efficient upsert with ON CONFLICT

---

## Phase 2: Source Decorator & Access Control Module

### Task 2.1: Add `supports_access_control` to Source Decorator

**File**: `backend/airweave/platform/decorators.py`

```python
def source(
    name: str,
    short_name: str,
    auth_methods: List[AuthenticationMethod],
    # ... existing params ...
    supports_access_control: bool = False,  # NEW
) -> Callable[[type], type]:
    """Enhanced source decorator with access control support.

    Args:
        # ... existing args ...
        supports_access_control: Whether this source provides entity-level access
            control metadata. When True, the source must:
            1. Set entity.access on all yielded entities
            2. Implement generate_access_control_memberships() method
            Default is False (entities visible to everyone).
    """
    def decorator(cls: type) -> type:
        # ... existing code ...
        cls._supports_access_control = supports_access_control
        return cls
    return decorator
```

### Task 2.2: Create Access Control Package

**Source**: `airweave-access-controls/backend/airweave/platform/access_control/`
**Target**: `airweave-sharepoint-vespa/backend/airweave/platform/access_control/`

```
Action: Copy entire directory
Files:
  - __init__.py
  - schemas.py (AccessControlMembership schema, AccessContext)
  - broker.py (AccessBroker class)
```

**Verify no conflicts**: The Vespa branch shouldn't have this directory.

### Task 2.3: Update AccessBroker for Source Awareness

The `AccessBroker` should be aware that some sources don't support access control:

```python
class AccessBroker:
    async def resolve_access_context_for_collection(
        self, db, user_principal: str, collection_id: UUID, organization_id: UUID
    ) -> Optional[AccessContext]:
        """Resolve access context, or None if collection has no AC sources."""

        # Check if any source in collection supports access control
        sources_with_ac = await self._get_ac_sources_in_collection(db, collection_id)

        if not sources_with_ac:
            return None  # No access control → don't filter

        # ... existing resolution logic ...
        return AccessContext(all_principals=[...])
```

---

## Phase 3: Sync Pipeline Integration (IMPLEMENTED)

> **Status**: ✅ Implemented with generic types architecture

### What We Built

We implemented a **generic types architecture** that shares structure between entity and access control (AC) sync pipelines while allowing domain-specific extensions.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     GENERIC BASE TYPES (types.py)                        │
├─────────────────────────────────────────────────────────────────────────┤
│  BaseAction[T]                                                           │
│  ├── InsertAction[T]                                                     │
│  ├── UpdateAction[T]                                                     │
│  ├── DeleteAction[T]                                                     │
│  ├── KeepAction[T]                                                       │
│  └── UpsertAction[T]                                                     │
│                                                                          │
│  ActionBatch[T]  (container with inserts, updates, deletes, etc.)        │
└─────────────────────────────────────────────────────────────────────────┘
                    │                              │
                    ▼                              ▼
┌─────────────────────────────────┐   ┌─────────────────────────────────┐
│  ENTITY TYPES (entity_types.py) │   │    AC TYPES (ac_types.py)       │
├─────────────────────────────────┤   ├─────────────────────────────────┤
│  EntityInsertAction             │   │  ACInsertAction                 │
│  (extends InsertAction[Entity]) │   │  (extends InsertAction[Tuple])  │
│  + entity_definition_id         │   │  + convenience properties       │
│  + chunk_entities               │   │                                 │
│                                 │   │  ACUpsertAction (main action)   │
│  EntityActionBatch              │   │  ACActionBatch                  │
│  + existing_map                 │   │                                 │
└─────────────────────────────────┘   └─────────────────────────────────┘
```

### Why Generics?

We use Python generics (like the CRUD layer) to:

1. **Share structure** - Both pipelines use `InsertAction`, `ActionBatch`, etc.
2. **Allow extension** - Entity types add `entity_definition_id`, `chunk_entities`
3. **Single protocol** - One `ActionHandler[T, B]` protocol for both

**Compare to CRUD layer:**
```python
# CRUD uses generics for Model, CreateSchema, UpdateSchema
class CRUDBaseOrganization(Generic[ModelType, CreateSchemaType, UpdateSchemaType])

# Sync uses generics for Payload type and Batch type
class ActionHandler(Protocol, Generic[T, B])
```

### File Structure (Actual Implementation)

```
platform/sync/
├── actions/
│   ├── __init__.py                      # Exports all types
│   ├── types.py                         # Generic base: BaseAction[T], ActionBatch[T]
│   ├── entity_types.py                  # EntityInsertAction, EntityActionBatch
│   ├── access_control_types.py          # ACInsertAction, ACUpsertAction, ACActionBatch
│   ├── entity_resolver.py               # EntityActionResolver
│   ├── entity_dispatcher.py             # EntityActionDispatcher
│   ├── access_control_resolver.py       # ACActionResolver
│   └── access_control_dispatcher.py     # ACActionDispatcher
├── handlers/
│   ├── __init__.py
│   ├── protocol.py                      # ActionHandler[T, B] generic protocol
│   ├── destination.py                   # DestinationHandler (entity)
│   ├── arf.py                           # ArfHandler (entity)
│   ├── entity_postgres.py               # EntityPostgresHandler
│   └── access_control_postgres.py       # ACPostgresHandler
├── entity_pipeline.py
└── access_control_pipeline.py
```

### Naming Convention: Entity vs AC

| Component | Entity Sync | Access Control Sync |
|-----------|-------------|---------------------|
| Base types | `InsertAction[T]`, etc. | (same generic types) |
| Concrete types | `EntityInsertAction` | `ACInsertAction`, `ACUpsertAction` |
| Batch | `EntityActionBatch` | `ACActionBatch` |
| Resolver | `EntityActionResolver` | `ACActionResolver` |
| Dispatcher | `EntityActionDispatcher` | `ACActionDispatcher` |
| Handler | `DestinationHandler`, `EntityPostgresHandler` | `ACPostgresHandler` |
| Pipeline | `EntityPipeline` | `AccessControlPipeline` |

### Generic Protocol

```python
# handlers/protocol.py
T = TypeVar("T")  # Payload type (BaseEntity or MembershipTuple)
B = TypeVar("B")  # Batch type (EntityActionBatch or ACActionBatch)

class ActionHandler(Protocol, Generic[T, B]):
    @property
    def name(self) -> str: ...

    async def handle_batch(self, batch: B, sync_context: "SyncContext") -> Any: ...
    async def handle_inserts(self, actions: List[InsertAction[T]], ...) -> Any: ...
    async def handle_updates(self, actions: List[UpdateAction[T]], ...) -> Any: ...
    async def handle_deletes(self, actions: List[DeleteAction[T]], ...) -> Any: ...
    async def handle_upserts(self, actions: List[UpsertAction[T]], ...) -> Any: ...
    async def handle_orphan_cleanup(self, orphan_ids: List[str], ...) -> Any: ...

# Type aliases for convenience
EntityActionHandler = ActionHandler["BaseEntity", "EntityActionBatch"]
ACActionHandler = ActionHandler["MembershipTuple", "ACActionBatch"]
```

### Why Handlers Use Concrete Types

Even though we have generic base types, handlers use **concrete types** because they need domain-specific fields:

```python
# Entity handler needs entity_definition_id (not on generic InsertAction)
class EntityPostgresHandler:
    async def handle_inserts(self, actions: List[EntityInsertAction], ...):
        for action in actions:
            schemas.EntityCreate(
                entity_definition_id=action.entity_definition_id,  # Entity-specific!
                entity_id=action.entity_id,
                ...
            )

# AC handler uses simpler types (no extra fields needed)
class ACPostgresHandler:
    async def handle_upserts(self, actions: List[ACUpsertAction], ...):
        memberships = [action.membership for action in actions]
        await crud.access_control_membership.bulk_create(...)
```

**Key insight:** The generic base provides the **pattern**, but domain-specific code needs **concrete types** with their extra fields.

### Entity Types (entity_types.py)

```python
@dataclass
class EntityInsertAction(InsertAction["BaseEntity"]):
    """Extends generic InsertAction with entity-specific fields."""
    entity_definition_id: UUID = field(default=None)
    chunk_entities: List["BaseEntity"] = field(default_factory=list)

    @property
    def entity(self) -> "BaseEntity":
        return self.payload

    @property
    def entity_id(self) -> str:
        return self.payload.entity_id

@dataclass
class EntityActionBatch(ActionBatch["BaseEntity"]):
    """Extends generic ActionBatch with existing_map for updates/deletes."""
    inserts: List[EntityInsertAction] = field(default_factory=list)
    updates: List[EntityUpdateAction] = field(default_factory=list)
    deletes: List[EntityDeleteAction] = field(default_factory=list)
    keeps: List[EntityKeepAction] = field(default_factory=list)

    existing_map: Dict[Tuple[str, UUID], "models.Entity"] = field(default_factory=dict)
```

### AC Types (access_control_types.py)

```python
@dataclass
class ACUpsertAction(UpsertAction["MembershipTuple"]):
    """Membership upsert - currently the only action used."""

    @property
    def membership(self) -> "MembershipTuple":
        return self.payload

    @property
    def member_id(self) -> str:
        return self.payload.member_id

@dataclass
class ACActionBatch(ActionBatch["MembershipTuple"]):
    """Container for AC actions - simpler than EntityActionBatch."""
    inserts: List[ACInsertAction] = field(default_factory=list)
    updates: List[ACUpdateAction] = field(default_factory=list)
    deletes: List[ACDeleteAction] = field(default_factory=list)
    keeps: List[ACKeepAction] = field(default_factory=list)
    upserts: List[ACUpsertAction] = field(default_factory=list)  # Currently used
```

### Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           ENTITY SYNC PIPELINE                                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│  Source.generate_entities()                                                      │
│           ↓                                                                      │
│  EntityActionResolver.resolve() → compares hashes                               │
│           ↓                                                                      │
│  EntityActionBatch(inserts=[...], updates=[...], deletes=[...], keeps=[...])    │
│           ↓                                                                      │
│  EntityActionDispatcher.dispatch() → to all handlers concurrently               │
│           ↓                                                                      │
│  DestinationHandler, ArfHandler, EntityPostgresHandler                          │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                      ACCESS CONTROL SYNC PIPELINE                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│  Source.generate_access_control_memberships()                                   │
│           ↓                                                                      │
│  ACActionResolver.resolve() → currently all become upserts                      │
│           ↓                                                                      │
│  ACActionBatch(upserts=[...])                                                   │
│           ↓                                                                      │
│  ACActionDispatcher.dispatch() → to handlers                                    │
│           ↓                                                                      │
│  ACPostgresHandler (future: + ACRedisHandler)                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Implementation Tasks (Completed)

| Task | Status | Description |
|------|--------|-------------|
| 3.1 | ✅ | Create generic base types (`types.py`) |
| 3.2 | ✅ | Create entity types extending generics (`entity_types.py`) |
| 3.3 | ✅ | Create AC types extending generics (`access_control_types.py`) |
| 3.4 | ✅ | Create generic `ActionHandler[T, B]` protocol |
| 3.5 | ✅ | Rename entity resolver/dispatcher with Entity prefix |
| 3.6 | ✅ | Create `ACActionResolver` |
| 3.7 | ✅ | Create `ACActionDispatcher` |
| 3.8 | ✅ | Create `ACPostgresHandler` implementing protocol |
| 3.9 | ✅ | Create `AccessControlPipeline` |
| 3.10 | ✅ | Add `_process_access_control_memberships()` to orchestrator |
| 3.11 | ✅ | Add `generate_access_control_memberships()` to BaseSource |

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Generic base types** | Share structure, reduce duplication |
| **Domain-specific extensions** | Entity needs extra fields (definition_id, chunks) |
| **Single generic protocol** | One interface, parameterized by types |
| **Concrete types in handlers** | Need access to domain-specific fields |
| **AC prefix (not Membership)** | Shorter, consistent with codebase style |
| **All AC action types defined** | Ready for future hash comparison, even if unused now |

### Future Extensibility

| Extension | Where to Add |
|-----------|--------------|
| **Redis handler** | `handlers/access_control_redis.py` implementing `ACActionHandler` |
| **Hash comparison** | `ACActionResolver` - query DB, return KEEP for unchanged |
| **Delete action** | Already defined in `access_control_types.py`, implement in handler |
| **New destination** | Create handler implementing `ActionHandler[T, B]` |

---

## Phase 4: Vespa Integration

### Task 4.1: Update Vespa Schema

**File**: `vespa/app/schemas/base_entity.sd`

Add access control fields:

```yaml
# Access Control Fields (only populated for sources with supports_access_control=True)
# For sources without AC, these fields will be absent and no filter is applied
field access_is_public type bool {
    indexing: attribute | summary
    attribute: fast-search
}

field access_viewers type array<string> {
    indexing: attribute | summary
    attribute: fast-search
}
```

**Also update** other schemas (file_entity.sd, etc.) if they don't inherit from base_entity.

### Task 4.2: Update VespaDestination._transform_entity()

**File**: `backend/airweave/platform/destinations/vespa.py`

**IMPORTANT**: Only include access fields if the entity has them set:

```python
def _transform_entity(self, entity: BaseEntity) -> Tuple[str, Dict[str, Any]]:
    # ... existing field extraction ...

    # Add access control fields ONLY if entity has access metadata
    # Sources without supports_access_control=True won't set this field,
    # and we don't want to add default restrictive values that would hide entities
    if entity.access is not None:
        fields["access_is_public"] = entity.access.is_public
        fields["access_viewers"] = entity.access.viewers if entity.access.viewers else []
    # else: don't add access fields - entity is from non-AC source

    return schema_name, {"id": doc_id, "fields": fields}
```

### Task 4.3: Update VespaDestination Filter Translation

**File**: `backend/airweave/platform/destinations/vespa.py`

Handle the `any` operator for array matching:

```python
def _translate_match_condition(self, condition: Dict[str, Any]) -> str:
    """Translate a match condition to YQL."""
    key = self._map_field_name(condition["key"])
    match = condition["match"]

    # Handle "any" operator for array fields (access control)
    if isinstance(match, dict) and "any" in match:
        values = match["any"]
        if not values:
            return "false"  # No principals = no access
        # Generate: (field contains "v1" OR field contains "v2" OR ...)
        clauses = [f'{key} contains "{self._escape_yql_string(v)}"' for v in values]
        return f"({' OR '.join(clauses)})"

    # Handle simple value match
    if isinstance(match, dict) and "value" in match:
        value = match["value"]
        if isinstance(value, bool):
            return f"{key} = {'true' if value else 'false'}"
        elif isinstance(value, str):
            return f'{key} contains "{self._escape_yql_string(value)}"'
        else:
            return f"{key} = {value}"

    # ... rest of existing logic ...

def _map_field_name(self, key: str) -> str:
    """Map Airweave field names to Vespa field names."""
    # Access control field mapping
    if key == "access.is_public":
        return "access_is_public"
    if key == "access.viewers":
        return "access_viewers"

    # ... existing mappings ...

def _escape_yql_string(self, value: str) -> str:
    """Escape special characters for YQL string literals."""
    return value.replace("\\", "\\\\").replace('"', '\\"')
```

---

## Phase 5: Search Integration

### Task 5.1: Update Search to be Access Control Aware

**File**: `backend/airweave/search/operations/user_filter.py` (or wherever filtering happens)

Only apply access control filter when needed:

```python
async def build_search_filter(
    db: AsyncSession,
    collection_id: UUID,
    user: User,
    base_filter: Optional[Dict],
) -> Optional[Dict]:
    """Build search filter, including access control if applicable."""

    # Resolve access context (returns None if no AC sources in collection)
    access_context = await access_broker.resolve_access_context_for_collection(
        db=db,
        user_principal=f"user:{user.email}",
        collection_id=collection_id,
        organization_id=user.organization_id,
    )

    if access_context is None:
        # Collection has no sources with access control
        # Return base filter unchanged (no access filtering)
        return base_filter

    # Build access control filter
    access_filter = {
        "should": [
            {"key": "access.is_public", "match": {"value": True}},
            {"key": "access.viewers", "match": {"any": access_context.all_principals}},
        ]
    }

    # Combine with base filter
    if base_filter:
        return {"must": [base_filter, access_filter]}
    return access_filter
```

### Task 5.2: Handle Mixed Collections (AC + non-AC sources)

When a collection has BOTH access-control and non-access-control sources:

```python
# Access filter that handles mixed sources:
# - AC sources: filter by is_public OR viewers
# - Non-AC sources: no access fields → should be visible

access_filter = {
    "should": [
        # Entity is public
        {"key": "access.is_public", "match": {"value": True}},
        # Entity has user in viewers
        {"key": "access.viewers", "match": {"any": access_context.all_principals}},
        # Entity has no access field at all (non-AC source) - NEEDS VESPA SUPPORT
        # This might require a "field_exists" check or default value handling
    ]
}
```

**Note**: This may require Vespa schema changes to handle missing fields gracefully. We may need to:
- Add a `has_access_control` boolean field, OR
- Use Vespa's `!isNull(access_is_public)` in YQL

---

## Phase 6: SharePoint 2019 V2 Source (Required) ✅ COMPLETED

This is a **required** part of the goal, not optional.

### What Was Implemented

**Task 6.1: Ported SharePoint 2019 V2 Source Directory**

Created the entire source package at `backend/airweave/platform/sources/sharepoint2019v2/`:

| File | Purpose |
|------|---------|
| `__init__.py` | Package exports |
| `source.py` | Main source class with `generate_entities()` and `generate_access_control_memberships()` |
| `client.py` | SharePoint REST API client with NTLM auth |
| `acl.py` | Access control helpers for role assignment processing |
| `ldap.py` | Active Directory LDAP client for group expansion |
| `builders.py` | Entity builder functions for sites, lists, items, files |

**Key changes from POC:**
- Updated imports to use `MembershipTuple` instead of `AccessControlMembership` for sync processing
- All membership generation now yields `MembershipTuple` instances

**Task 6.2: Updated SharePoint Source Decorator**

Added `supports_access_control=True` to the `@source` decorator:

```python
@source(
    name="SharePoint 2019 On-Premise V2",
    short_name="sharepoint2019v2",
    auth_methods=[AuthenticationMethod.DIRECT],
    auth_config_class="SharePoint2019V2AuthConfig",
    config_class="SharePoint2019V2Config",
    supports_continuous=False,
    supports_access_control=True,  # ← Enables access control sync
)
class SharePoint2019V2Source(BaseSource):
```

**Task 6.3: Added SharePoint Config Classes**

Added to `backend/airweave/platform/configs/auth.py`:
- `SharePoint2019V2AuthConfig` with NTLM + LDAP credentials

Added to `backend/airweave/platform/configs/config.py`:
- `SharePoint2019V2Config` with site_url, ad_server, ad_search_base

**Task 6.4: Registered SharePoint2019V2 Entities**

Created `backend/airweave/platform/entities/sharepoint2019v2.py` with:
- `SharePoint2019V2SiteEntity`
- `SharePoint2019V2ListEntity`
- `SharePoint2019V2ItemEntity`
- `SharePoint2019V2FileEntity`

Updated `backend/airweave/platform/entities/__init__.py` to export these entities.

**Note:** No `integrations.yaml` update needed - sources are auto-discovered via the `@source` decorator.

---

## Testing Plan

### Unit Tests

| Test | Description |
|------|-------------|
| `test_access_broker_resolve` | User gets correct expanded principals |
| `test_access_broker_nested_groups` | Nested groups expand correctly |
| `test_access_broker_no_ac_sources` | Returns None for collections without AC |
| `test_vespa_filter_translation` | Access filter translates to valid YQL |
| `test_vespa_filter_any_operator` | `{"any": [...]}` generates correct YQL |
| `test_qdrant_filter_passthrough` | Access filter works with Qdrant |
| `test_entity_with_access_control` | Entity serializes access field correctly |
| `test_source_decorator_ac_flag` | Decorator sets `_supports_access_control` |

### Integration Tests

| Test | Description |
|------|-------------|
| `test_sync_with_access_control` | Full sync includes membership processing |
| `test_sync_without_access_control` | Regular source skips AC phase |
| `test_search_public_entity` | Public entities visible to all |
| `test_search_private_entity_authorized` | User with access can find entity |
| `test_search_private_entity_unauthorized` | User without access cannot find entity |
| `test_search_non_ac_source` | Entities from Slack etc. always visible |
| `test_membership_cascade_delete` | Deleting source removes memberships |

---

## Migration Checklist

### Pre-merge
- [ ] Run database migration on dev environment
- [ ] Verify Vespa schema deploys correctly
- [ ] Run unit tests
- [ ] Run integration tests

### Post-merge
- [ ] Deploy database migration to staging
- [ ] Deploy Vespa schema changes
- [ ] Verify existing syncs still work (no access control = no filtering)
- [ ] Test SharePoint 2019 V2 source with access control
- [ ] Monitor for performance issues (AccessBroker queries)

---

## Implementation Order

Recommended order to minimize risk:

```
Week 1: Foundation (Phases 1-2)
  ├── Task 1.1: AccessControlMembership model ✅
  ├── Task 1.2: Database migration ✅
  ├── Task 1.3: BaseEntity.access field ✅
  ├── Task 1.4: CRUD layer ✅
  ├── Task 2.1: Source decorator flag ✅
  ├── Task 2.2: Access control package ✅
  ├── Task 2.3: AccessBroker updates ✅
  └── Task 2.4: Add supports_access_control to Source model/schema ✅

Week 2: Sync Pipeline (Phase 3) ✅ IMPLEMENTED
  ├── Task 3.1: Create generic base types (types.py) ✅
  ├── Task 3.2: Create entity types extending generics (entity_types.py) ✅
  ├── Task 3.3: Create AC types extending generics (access_control_types.py) ✅
  ├── Task 3.4: Create generic ActionHandler[T, B] protocol ✅
  ├── Task 3.5: Rename entity resolver/dispatcher with Entity prefix ✅
  ├── Task 3.6: Create ACActionResolver ✅
  ├── Task 3.7: Create ACActionDispatcher ✅
  ├── Task 3.8: Create ACPostgresHandler implementing protocol ✅
  ├── Task 3.9: Create AccessControlPipeline ✅
  ├── Task 3.10: Add _process_access_control_memberships() to orchestrator ✅
  └── Task 3.11: Add generate_access_control_memberships() to BaseSource ✅

Week 3: Vespa & Search (Phases 4-5)
  ├── Task 4.1: Vespa schema updates
  ├── Task 4.2: Transform entities with access fields
  ├── Task 4.3: Filter translation for access control
  ├── Task 5.1: Search filter building
  └── Task 5.2: Mixed collection handling

Week 4: SharePoint Source (Phase 6)
  ├── Task 6.1: Port SharePoint 2019 V2 source
  ├── Task 6.2: Update SharePoint decorator
  ├── Task 6.3: Port SharePoint config classes
  └── Task 6.4: Update integrations.yaml

Week 5: Testing & Validation
  ├── Unit tests for new components
  ├── Integration tests
  └── Manual testing with SharePoint
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Migration conflicts | Medium | Medium | Careful revision ID management |
| AccessBroker performance | Medium | High | Add caching layer later |
| Vespa YQL filter errors | Medium | Medium | Comprehensive test coverage |
| Breaking existing sources | **Low** | **High** | Source decorator flag + careful filter logic |
| Mixed collection edge cases | Medium | Medium | Explicit `has_access_control` field |

---

## Resolved Questions

| Question | Decision |
|----------|----------|
| Use new handler/dispatcher for AC? | **YES** - for future extensibility (Redis, delete actions) even if simpler today |
| Default behavior for entities without `access`? | **No filter** - entities visible to everyone |
| How to distinguish AC vs non-AC sources? | **Decorator flag**: `supports_access_control=True` |
| What if AC source yields entity without `access`? | **Warning** - should validate and log |
| How to name Entity vs AC components? | **Prefixes**: `EntityActionBatch` vs `ACActionBatch` (AC, not Membership) |
| Keep backwards compatibility? | **No** - renamed classes directly, updated all imports |
| Where to put AC sync files? | **Same location** - `platform/sync/` alongside entity sync files |
| Handler structure for extensibility? | **Yes** - separate `_handle_upserts()`, `_handle_deletes()` methods |
| How to share types between Entity and AC? | **Generics** - `InsertAction[T]` base with `EntityInsertAction` extensions |
| Why separate protocols? | **Not needed** - single `ActionHandler[T, B]` with type aliases |
| Why handlers use concrete types? | **Need domain-specific fields** - `entity_definition_id`, `chunk_entities` |

---

## Files Reference

### Files to Copy (minimal changes)
```
airweave-access-controls/backend/airweave/models/access_control_membership.py
airweave-access-controls/backend/airweave/crud/crud_access_control_membership.py
airweave-access-controls/backend/airweave/platform/access_control/broker.py (adapt for new arch)
airweave-access-controls/backend/airweave/platform/sources/sharepoint2019v2/ (entire dir)
```

### Files to Modify
```
# Phase 1: Database & Models
airweave-sharepoint-vespa/backend/airweave/models/__init__.py
airweave-sharepoint-vespa/backend/airweave/crud/__init__.py
airweave-sharepoint-vespa/backend/airweave/platform/entities/_base.py

# Phase 2: Decorator & Access Control Module
airweave-sharepoint-vespa/backend/airweave/platform/decorators.py
airweave-sharepoint-vespa/backend/airweave/models/source.py
airweave-sharepoint-vespa/backend/airweave/schemas/source.py
airweave-sharepoint-vespa/backend/airweave/platform/db_sync.py

# Phase 3: Sync Pipeline (implemented with generic types)
airweave-sharepoint-vespa/backend/airweave/platform/sync/actions/__init__.py     # Export all types
airweave-sharepoint-vespa/backend/airweave/platform/sync/actions/entity_resolver.py   # Renamed from resolver.py
airweave-sharepoint-vespa/backend/airweave/platform/sync/actions/entity_dispatcher.py # Renamed from dispatcher.py
airweave-sharepoint-vespa/backend/airweave/platform/sync/handlers/__init__.py    # Export handlers + protocol
airweave-sharepoint-vespa/backend/airweave/platform/sync/handlers/protocol.py    # Generic ActionHandler[T, B]
airweave-sharepoint-vespa/backend/airweave/platform/sync/handlers/entity_postgres.py # Renamed from postgres.py
airweave-sharepoint-vespa/backend/airweave/platform/sync/handlers/destination.py     # Updated imports
airweave-sharepoint-vespa/backend/airweave/platform/sync/handlers/arf.py             # Updated imports
airweave-sharepoint-vespa/backend/airweave/platform/sync/orchestrator.py
airweave-sharepoint-vespa/backend/airweave/platform/sources/_base.py

# Phase 4: Vespa
airweave-sharepoint-vespa/backend/airweave/platform/destinations/vespa.py
airweave-sharepoint-vespa/vespa/app/schemas/base_entity.sd

# Phase 5: Search
airweave-sharepoint-vespa/backend/airweave/search/operations/user_filter.py
```

### Files to Create
```
# Phase 1
airweave-sharepoint-vespa/backend/alembic/versions/xxx_add_access_control_membership.py
airweave-sharepoint-vespa/backend/alembic/versions/xxx_add_supports_access_control_to_source.py

# Phase 2
airweave-sharepoint-vespa/backend/airweave/platform/access_control/__init__.py
airweave-sharepoint-vespa/backend/airweave/platform/access_control/schemas.py
airweave-sharepoint-vespa/backend/airweave/platform/access_control/broker.py

# Phase 3 (Implemented - generic types architecture)
airweave-sharepoint-vespa/backend/airweave/platform/sync/actions/types.py                    # Generic base types
airweave-sharepoint-vespa/backend/airweave/platform/sync/actions/entity_types.py             # Entity-specific extensions
airweave-sharepoint-vespa/backend/airweave/platform/sync/actions/access_control_types.py     # AC-specific extensions
airweave-sharepoint-vespa/backend/airweave/platform/sync/actions/access_control_resolver.py  # ACActionResolver
airweave-sharepoint-vespa/backend/airweave/platform/sync/actions/access_control_dispatcher.py # ACActionDispatcher
airweave-sharepoint-vespa/backend/airweave/platform/sync/handlers/access_control_postgres.py  # ACPostgresHandler
airweave-sharepoint-vespa/backend/airweave/platform/sync/access_control_pipeline.py          # AccessControlPipeline
```
