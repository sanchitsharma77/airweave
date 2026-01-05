# Vespa Integration & Sync Refactor - Branch Overview

> **Branch**: `feat/merge-sharepoint-vespa`
> **Branched from main**: December 5, 2025 (commit `0d45f182`)
> **Latest commits**: January 4, 2026
> **Purpose**: Add Vespa as a destination + refactor sync module with builder/handler pattern

---

## Executive Summary

This branch introduces two major changes:

1. **Vespa as a new vector database destination** - Vespa handles chunking and embedding server-side, enabling different processing requirements per destination
2. **Sync module refactor** - New builder/context/handler/processor architecture for cleaner separation of concerns

---

## Part 1: Vespa Destination

### Overview

Vespa is a new `VectorDBDestination` that differs from Qdrant in a key way: **Vespa handles chunking and embedding server-side**. This means Airweave only needs to send the raw text, and Vespa's schema definition handles the rest.

### Key Files

| File | Purpose |
|------|---------|
| `backend/airweave/platform/destinations/vespa.py` | Main destination implementation (~1000 lines) |
| `vespa/app/schemas/base_entity.sd` | Vespa schema with chunking, embedding, ranking |
| `vespa/app/services.xml` | Vespa service configuration |
| `vespa/deploy.sh` | Deployment script |

### Processing Requirement System

The destination declares what processing it needs via a class variable:

```python
class ProcessingRequirement(Enum):
    CHUNKS_AND_EMBEDDINGS = "chunks_and_embeddings"  # Qdrant, Pinecone
    TEXT_ONLY = "text_only"                          # Vespa
    RAW = "raw"                                      # S3
```

VespaDestination uses `TEXT_ONLY`:

```python
@destination("Vespa", "vespa", ...)
class VespaDestination(VectorDBDestination):
    processing_requirement = ProcessingRequirement.TEXT_ONLY
```

### Entity Transformation

Vespa requires a specific document format. The `VespaDestination._transform_entity()` method:

1. **Determines schema** - Maps entity class to Vespa schema name:
   - `BaseEntity` → `base_entity`
   - `FileEntity` → `file_entity`
   - `CodeFileEntity` → `code_file_entity`
   - `EmailEntity` → `email_entity`
   - `WebEntity` → `web_entity`

2. **Builds fields** - Extracts and flattens entity data:
   - Base fields: `entity_id`, `name`, `breadcrumbs`, `created_at`, `updated_at`
   - System metadata: Flattened with `airweave_system_metadata_` prefix
   - Type-specific fields: `url`, `crawl_url`, `repo_name`, etc.
   - Payload: Everything else as JSON string

3. **Returns document** - `(schema_name, {"id": doc_id, "fields": {...}})`

### Bulk Insert (Feed)

Uses pyvespa's `feed_iterable` for efficient concurrent feeding:

```python
async def bulk_insert(self, entities: list[BaseEntity]) -> None:
    # Transform entities grouped by schema
    docs_by_schema = self._transform_entities_by_schema(entities)

    # Feed each schema's documents (runs in thread pool)
    for schema, docs in docs_by_schema.items():
        await asyncio.to_thread(_feed_schema_sync, schema, docs)
```

**Important**: pyvespa is synchronous, so all calls are wrapped in `asyncio.to_thread()`.

### Search Implementation

Vespa search uses YQL (Vespa Query Language) with hybrid retrieval:

```python
async def search(
    self,
    queries: List[str],                    # Supports query expansion
    airweave_collection_id: UUID,
    limit: int,
    offset: int,
    filter: Optional[Dict[str, Any]],      # Airweave canonical format
    ...
) -> List[SearchResult]:
```

**YQL Construction** (`_build_search_yql`):

```sql
SELECT * FROM base_entity WHERE
  airweave_system_metadata_collection_id contains '{collection_id}' AND
  (({targetHits:400}userInput(@query)) OR
   ({label:"q0", targetHits:400}nearestNeighbor(chunk_small_embeddings, q0)) OR
   ({label:"q1", targetHits:400}nearestNeighbor(chunk_small_embeddings, q1))) AND
  ({user_filter})
```

**Multi-Query Support**: When query expansion provides multiple queries, each gets its own `nearestNeighbor` operator combined with OR.

### Filter Translation

**Critical for Access Control**: Vespa translates Airweave's canonical filter format (Qdrant-style) to YQL:

```python
def translate_filter(self, filter: Optional[Dict[str, Any]]) -> Optional[str]:
    """Translate Airweave filter to Vespa YQL filter string."""
```

**Translation Rules**:
| Airweave Format | Vespa YQL |
|-----------------|-----------|
| `{"must": [...]}` | `(... AND ...)` |
| `{"should": [...]}` | `(... OR ...)` |
| `{"must_not": [...]}` | `!(... AND ...)` |
| `{"key": "field", "match": {"value": "x"}}` | `field contains "x"` |
| `{"key": "field", "range": {"gt": 10}}` | `field > 10` |

**Field Name Mapping**:
```python
meta_field_map = {
    "collection_id": "airweave_system_metadata_collection_id",
    "entity_type": "airweave_system_metadata_entity_type",
    "source_name": "airweave_system_metadata_source_name",
    # ... etc
}
```

### Vespa Schema (base_entity.sd)

Key features relevant to filtering and search:

```yaml
# System metadata fields - all have fast-search for filtering
field airweave_system_metadata_collection_id type string {
    indexing: attribute | summary
    attribute: fast-search
}

# Chunking and embedding happens server-side
field chunks type array<string> {
    indexing: input textual_representation | chunk fixed-length 1024 | summary | index
    index: enable-bm25
}

field chunk_small_embeddings type tensor<int8>(chunk{}, x[96]) {
    indexing: input textual_representation | chunk fixed-length 1024 | embed | pack_bits | attribute | index
}
```

**Ranking Profile** (`hybrid-rrf`):
- First phase: BM25 + ANN closeness
- Second phase: Per-chunk cosine similarity with large embeddings
- Global phase: RRF (Reciprocal Rank Fusion)

---

## Part 2: Sync Module Refactor

### Complete Execution Flow (Step-by-Step)

Here's exactly what happens from start to finish when a sync runs:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           INITIALIZATION (Factory)                               │
├─────────────────────────────────────────────────────────────────────────────────┤
│  1. SyncContextBuilder creates SyncContext with all sub-contexts               │
│  2. DestinationsContextBuilder creates destinations from sync.destination_ids   │
│     → Looks up each destination_connection_id in database                       │
│     → Creates Qdrant, Vespa, S3 instances based on what's configured           │
│  3. DispatcherBuilder creates ActionDispatcher with handlers                    │
│  4. EntityPipeline created with ActionResolver + ActionDispatcher              │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           ORCHESTRATOR.RUN()                                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│  Phase 1: Start sync job                                                        │
│  Phase 2: Process entities (see detail below)                                   │
│  Phase 3: Cleanup orphaned entities                                             │
│  Phase 4: Complete sync, save cursor                                            │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     PHASE 2: PROCESS ENTITIES (Detail)                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   SOURCE generates entities one-by-one via async generator                       │
│                          │                                                       │
│                          ▼                                                       │
│   ORCHESTRATOR batches entities (size-based or time-based flush)                │
│   - Accumulates into batch_buffer[]                                             │
│   - Flushes when: batch_size reached OR max_batch_latency_ms exceeded           │
│                          │                                                       │
│                          ▼                                                       │
│   WORKER POOL submits batch to EntityPipeline.process()                         │
│   - Up to max_workers batches processed concurrently                            │
│                          │                                                       │
│                          ▼                                                       │
│   ┌──────────────────────────────────────────────────────────────────────────┐  │
│   │                    ENTITY PIPELINE (per batch)                            │  │
│   ├──────────────────────────────────────────────────────────────────────────┤  │
│   │  Step 1: TRACK & DEDUPE                                                   │  │
│   │  - EntityTracker records each entity_id                                   │  │
│   │  - Skips duplicates (same entity_id seen twice in same sync)             │  │
│   │                                                                           │  │
│   │  Step 2: PREPARE                                                          │  │
│   │  - Enrich with metadata (sync_id, entity_type, source_name)              │  │
│   │  - Compute content hash                                                   │  │
│   │                                                                           │  │
│   │  Step 3: RESOLVE ACTIONS (ActionResolver)                                 │  │
│   │  - Query Postgres: "what hashes exist for these entity_ids?"             │  │
│   │  - Compare: new hash vs stored hash                                       │  │
│   │  - Output: ActionBatch with lists of:                                     │  │
│   │      • InsertAction (new entity, not in DB)                              │  │
│   │      • UpdateAction (hash changed)                                        │  │
│   │      • DeleteAction (DeletionEntity from source)                         │  │
│   │      • KeepAction (hash unchanged → skip processing)                     │  │
│   │                                                                           │  │
│   │  Step 4: EARLY EXIT                                                       │  │
│   │  - If all actions are KEEP → return (nothing to do)                      │  │
│   │                                                                           │  │
│   │  Step 5: DISPATCH (ActionDispatcher)                                      │  │
│   │  - See "DISPATCH DETAIL" below                                           │  │
│   │                                                                           │  │
│   │  Step 6: UPDATE TRACKER                                                   │  │
│   │  - Record inserted/updated/deleted counts                                 │  │
│   │  - Publish progress via Redis pubsub                                      │  │
│   └──────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Dispatch Detail: How Handlers and Processors Work

This is the key part that answers "which destination is used?" and "how are entities processed?":

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         DISPATCH (ActionDispatcher)                              │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   ActionBatch arrives with: inserts[], updates[], deletes[], keeps[]            │
│                                                                                  │
│   ┌─────────────────── CONCURRENT ────────────────────┐                         │
│   │                                                    │                         │
│   │   DestinationHandler              ArfHandler       │                         │
│   │   (handles ALL destinations)      (raw storage)    │                         │
│   │          │                              │          │                         │
│   │          ▼                              ▼          │                         │
│   │   For EACH destination           Store raw entity  │                         │
│   │   in destinations[]:             in ARF format     │                         │
│   │          │                                         │                         │
│   │          ▼                                         │                         │
│   │   ┌─────────────────────────────────────────┐     │                         │
│   │   │  PROCESSOR SELECTION                     │     │                         │
│   │   │                                          │     │                         │
│   │   │  Check destination.processing_requirement│     │                         │
│   │   │                                          │     │                         │
│   │   │  CHUNKS_AND_EMBEDDINGS? (Qdrant)         │     │                         │
│   │   │    → ChunkEmbedProcessor                 │     │                         │
│   │   │    → text → chunks → embeddings          │     │                         │
│   │   │                                          │     │                         │
│   │   │  TEXT_ONLY? (Vespa)                      │     │                         │
│   │   │    → TextOnlyProcessor                   │     │                         │
│   │   │    → just build textual_representation   │     │                         │
│   │   │                                          │     │                         │
│   │   │  RAW? (S3)                               │     │                         │
│   │   │    → RawProcessor                        │     │                         │
│   │   │    → pass through unchanged              │     │                         │
│   │   └─────────────────────────────────────────┘     │                         │
│   │          │                                         │                         │
│   │          ▼                                         │                         │
│   │   destination.bulk_insert(processed_entities)     │                         │
│   │                                                    │                         │
│   └────────────────────────────────────────────────────┘                         │
│                              │                                                   │
│                              ▼                                                   │
│              ALL SUCCEEDED? ───NO───> Raise SyncFailureError                    │
│                              │                                                   │
│                             YES                                                  │
│                              │                                                   │
│                              ▼                                                   │
│   ┌─────────────────── SEQUENTIAL ────────────────────┐                         │
│   │                                                    │                         │
│   │   PostgresMetadataHandler                          │                         │
│   │   - Persist entity metadata to entity table        │                         │
│   │   - Only runs AFTER destinations succeed           │                         │
│   │                                                    │                         │
│   └────────────────────────────────────────────────────┘                         │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### What Determines Which Destinations Are Used?

**Answer**: The `Sync` record in the database has a `destination_connection_ids` field (list of UUIDs). During initialization:

```python
# In DestinationsContextBuilder._create_destinations():
for destination_connection_id in sync.destination_connection_ids:
    # Look up DestinationConnection in DB
    dest_conn = await crud.destination_connection.get(db, id=destination_connection_id)

    # Get destination class (Qdrant, Vespa, S3) based on short_name
    destination_class = resource_locator.get_destination_class(dest_conn.short_name)

    # Create instance with credentials and config
    destination = await destination_class.create(
        credentials=decrypted_creds,
        config=dest_conn.config,
        collection_id=collection.id,
        ...
    )
    destinations.append(destination)
```

**So**: If a sync has `destination_connection_ids = [qdrant_uuid, vespa_uuid]`, BOTH Qdrant AND Vespa will receive the data. The `DestinationHandler` iterates over ALL destinations and processes each one with its appropriate processor.

### Why This Design?

1. **Same data → Multiple destinations**: One sync can write to Qdrant for search + S3 for backup
2. **Each destination controls its own processing**: Qdrant needs chunking+embeddings, Vespa just needs text, S3 needs raw
3. **All-or-nothing consistency**: If Vespa fails, Postgres metadata is NOT written, so you don't have orphan metadata

### Directory Structure

```
platform/
├── builders/           # Factory classes that construct contexts
│   ├── destinations.py # Creates destination instances from sync config
│   ├── dispatcher.py   # Creates ActionDispatcher with handlers
│   └── sync.py         # Orchestrates building full SyncContext
├── contexts/           # Dataclass containers for dependencies
│   ├── destinations.py # Holds destinations[] + entity_map
│   └── sync.py         # Full sync context (composes all sub-contexts)
└── sync/
    ├── handlers/       # Execute resolved actions
    │   ├── destination.py  # THE key handler - routes to all destinations
    │   ├── arf.py          # Raw entity storage
    │   └── postgres.py     # Metadata persistence (runs last)
    ├── processors/     # Content processing strategies
    │   ├── chunk_embed.py  # text → chunks → embeddings (Qdrant)
    │   ├── text_only.py    # text extraction only (Vespa)
    │   └── raw.py          # pass-through (S3)
    └── actions/        # Action types and dispatch
        ├── dispatcher.py   # Routes ActionBatch to handlers
        ├── resolver.py     # Determines INSERT/UPDATE/DELETE/KEEP
        └── types.py        # Action dataclasses
```

### Key Classes Summary

| Class | Responsibility |
|-------|---------------|
| `SyncOrchestrator` | Runs the sync: batches entities from source, submits to pipeline |
| `EntityPipeline` | Processes a batch: track → prepare → resolve → dispatch |
| `ActionResolver` | Compares hashes to DB, returns `ActionBatch` |
| `ActionDispatcher` | Routes `ActionBatch` to all handlers |
| `DestinationHandler` | For each destination: select processor → process → bulk_insert |
| `ChunkEmbedProcessor` | Converts entities to chunks with embeddings (for Qdrant) |
| `TextOnlyProcessor` | Builds `textual_representation` only (for Vespa) |
| `PostgresMetadataHandler` | Persists entity metadata (runs last, after destinations succeed) |

### Cleanup Service

Data cleanup is now centralized in `core/cleanup_service.py`:

```python
class CleanupService:
    async def cleanup_sync(self, db, sync_id, collection, ctx) -> None:
        """Clean up all data for a sync (source connection deletion)."""
        await self._cleanup_qdrant_by_sync(sync_id, collection, ctx)
        await self._cleanup_vespa_by_sync(sync_id, collection, ctx)
        await self._cleanup_arf(sync_id, ctx)

    async def cleanup_collection(self, db, collection, ctx) -> None:
        """Clean up all data for a collection."""
        await self._cleanup_qdrant_by_collection(collection, ctx)
        await self._cleanup_vespa_by_collection(collection, ctx)
```

---

## Integration Points for Access Control

### Overview: What Needs to Happen

To bring access control from the `poc/access-controls-on-data` branch into this refactored architecture:

**SYNC TIME** (write access control data):
1. Entity sync: Entities get `access` field with `viewers[]` and `is_public`
2. Membership sync: User→group and group→group tuples go to Postgres

**SEARCH TIME** (filter by access control):
1. Resolve user's principals via `AccessBroker`
2. Build filter that matches public OR user has access
3. Translate filter to destination format (Qdrant native / Vespa YQL)

### Where Access Control Fits in the Sync Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          ORCHESTRATOR.RUN() - Modified                           │
├─────────────────────────────────────────────────────────────────────────────────┤
│  Phase 1: Start sync job                                                        │
│  Phase 2: Process entities                                                       │
│         ↳ Entities now include entity.access = AccessControl(viewers=[...])     │
│         ↳ VespaDestination._transform_entity() must include access fields       │
│                                                                                  │
│  Phase 2.5: Process access control memberships  ← NEW PHASE                     │
│         ↳ source.generate_access_control_memberships() yields tuples            │
│         ↳ AccessControlPipeline persists to Postgres (no destinations)          │
│                                                                                  │
│  Phase 3: Cleanup orphaned entities                                             │
│  Phase 4: Complete sync                                                          │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Option A: Add Phase to Orchestrator (Simpler)

Minimal changes - just add a new phase after entity processing:

```python
# In orchestrator.py, after _process_entities():

async def _process_access_control_memberships(self) -> None:
    """Process access control memberships (Phase 2.5)."""
    if not hasattr(self.sync_context.source_instance, "generate_access_control_memberships"):
        return  # Source doesn't support access control

    # Use the existing AccessControlPipeline from the POC
    from airweave.platform.sync.access_control_pipeline import AccessControlPipeline
    pipeline = AccessControlPipeline()

    memberships = []
    async for membership in self.sync_context.source_instance.generate_access_control_memberships():
        memberships.append(membership)
        if len(memberships) >= self.batch_size:
            await pipeline.process(memberships, self.sync_context)
            memberships = []

    if memberships:
        await pipeline.process(memberships, self.sync_context)
```

**Why this works**: Access control memberships go to Postgres only, not to destinations. They don't need the handler/processor machinery.

### Option B: Add AccessControlHandler (More Consistent)

For consistency with the new architecture, create a handler:

```python
class AccessControlHandler(ActionHandler):
    """Handler for access control membership persistence."""

    @property
    def name(self) -> str:
        return "access_control"

    async def handle_batch(self, batch: ActionBatch, sync_context: SyncContext) -> None:
        # Access control doesn't use the action batch pattern
        # It has its own membership tuples
        pass

    async def handle_memberships(
        self, memberships: List[AccessControlMembership], sync_context: SyncContext
    ) -> None:
        """Persist membership tuples to Postgres."""
        await crud.access_control_membership.bulk_create(
            db=db,
            memberships=memberships,
            organization_id=sync_context.organization_id,
            source_connection_id=sync_context.connection.id,
            source_name=sync_context.connection.short_name,
        )
```

### Vespa Changes Needed

**1. Add access fields to `vespa/app/schemas/base_entity.sd`:**

```yaml
# Access control fields for filtering
field access_is_public type bool {
    indexing: attribute | summary
    attribute: fast-search
}

field access_viewers type array<string> {
    indexing: attribute | summary
    attribute: fast-search
}
```

**2. Update `VespaDestination._transform_entity()` to include access:**

```python
def _add_access_control_fields(self, fields: dict[str, Any], entity: BaseEntity) -> None:
    """Add access control fields if present."""
    if hasattr(entity, 'access') and entity.access:
        fields["access_is_public"] = entity.access.is_public
        fields["access_viewers"] = entity.access.viewers  # array<string>
```

**3. Update `VespaDestination._translate_match_condition()` for array matching:**

```python
def _translate_match_condition(self, condition: Dict[str, Any]) -> str:
    key = self._map_field_name(condition["key"])
    match = condition["match"]

    # Handle "any" operator for array fields (access control)
    if isinstance(match, dict) and "any" in match:
        values = match["any"]
        # Generate: field contains "v1" OR field contains "v2" OR ...
        clauses = [f'{key} contains "{v}"' for v in values]
        return f"({' OR '.join(clauses)})"

    # ... existing match handling
```

### Filter Translation Path (Search Time)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              SEARCH FLOW                                         │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   1. Search endpoint receives request                                            │
│                     │                                                            │
│                     ▼                                                            │
│   2. AccessBroker.resolve_access_context_for_collection()                       │
│      - Query Postgres for user's group memberships                              │
│      - Expand nested groups                                                      │
│      - Return AccessContext(all_principals=["user:x", "group:sp:42", ...])     │
│                     │                                                            │
│                     ▼                                                            │
│   3. UserFilter operation builds Airweave canonical filter:                     │
│      {                                                                           │
│        "should": [                                                               │
│          {"key": "access_is_public", "match": {"value": true}},                │
│          {"key": "access_viewers", "match": {"any": principals}}               │
│        ]                                                                         │
│      }                                                                           │
│                     │                                                            │
│                     ▼                                                            │
│   4. Retrieval calls destination.search(filter=...)                             │
│                     │                                                            │
│      ┌──────────────┴──────────────┐                                            │
│      ▼                              ▼                                            │
│   QDRANT                         VESPA                                          │
│   translate_filter()             translate_filter()                             │
│   returns as-is                  converts to YQL:                               │
│                                  (access_is_public = true OR                    │
│                                   access_viewers contains "user:x" OR           │
│                                   access_viewers contains "group:sp:42")        │
│                                                                                  │
│   5. Only authorized results returned                                           │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Checklist for Integration

- [ ] **Vespa schema**: Add `access_is_public` and `access_viewers` fields
- [ ] **VespaDestination**: Include access fields in `_transform_entity()`
- [ ] **VespaDestination**: Handle `{"match": {"any": [...]}}` in filter translation
- [ ] **Orchestrator**: Add `_process_access_control_memberships()` phase
- [ ] **Copy from POC**: `AccessControlPipeline`, `AccessControlMembership` model, CRUD
- [ ] **Copy from POC**: `AccessBroker`, `AccessContext`
- [ ] **Search endpoint**: Call `access_broker.resolve_access_context_for_collection()`
- [ ] **UserFilter**: Build filter with access principals (may already work from POC)
- [ ] **Test**: SharePoint source with access control → Search with user filtering

---

## Files Changed Summary

| Category | Files | Description |
|----------|-------|-------------|
| **Vespa Destination** | 1 file | New `vespa.py` (~1000 lines) |
| **Vespa Schema** | 5 files | Schema definitions, ranking profiles |
| **New Builders** | 8 files | Context factory classes |
| **New Contexts** | 9 files | Composable dependency containers |
| **New Handlers** | 4 files | Action execution handlers |
| **New Processors** | 5 files | Content processing strategies |
| **Search Changes** | 4 files | Destination-agnostic retrieval |
| **Base Destination** | 1 file | Added `ProcessingRequirement`, `translate_filter` |
| **Cleanup Service** | 1 file | Centralized data cleanup |

**Total**: ~95 files changed, ~7,400 lines added, ~3,500 lines removed

---

## Key Design Patterns

### 1. Strategy Pattern (Processors)
Destinations declare what they need, handlers use the appropriate processor.

### 2. Builder Pattern (Contexts)
Complex context construction is encapsulated in builder classes.

### 3. Protocol/Duck Typing (Handlers)
Handlers implement a protocol - easy to add new handlers without inheritance.

### 4. Dependency Injection
All major components receive dependencies via constructor, not global state.

### 5. All-or-Nothing Dispatch
If any destination handler fails, no Postgres writes occur.

---

## Testing Considerations

### Vespa-Specific Tests Needed
1. Filter translation (especially `should`/`OR` clauses for access control)
2. Entity transformation for all entity types
3. Multi-query search (query expansion)
4. Bulk insert with multiple schemas

### Sync Refactor Tests Needed
1. Handler execution order (destinations before Postgres)
2. Processor selection by `ProcessingRequirement`
3. Orphan cleanup through all handlers
4. Error propagation (all-or-nothing semantics)

---

## Next Steps for Access Control Integration

1. **Vespa schema update**: Add `access_is_public` and `access_viewers` fields
2. **Filter translation**: Handle `{"match": {"any": [...]}}` in Vespa
3. **Access control handler**: Implement handler for membership sync (or reuse existing POC pattern)
4. **Orchestrator hook**: Add membership processing phase after entity processing
5. **Test end-to-end**: Sync with access control → Search with filtering
