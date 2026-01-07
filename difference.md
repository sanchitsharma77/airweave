# Difference Overview: `feat/merge-sharepoint-vespa` vs `poc/vespa`

This document outlines the differences between the `feat/merge-sharepoint-vespa` branch and the `poc/vespa` branch to help with a selective merge. The goal is to bring Vespa-related improvements to `poc/vespa` **without** the access control feature.

---

## Summary

| Category | Can Merge to poc/vespa | Notes |
|----------|:---------------------:|-------|
| Vespa Destination Improvements | ✅ Yes | Core Vespa functionality |
| VespaChunkEmbedProcessor | ✅ Yes | Entity-as-document model |
| Matryoshka Embeddings | ✅ Yes | 768-dim + binary packing |
| Search Operations (non-ACL) | ✅ Yes | Debug logging, reranking |
| Sync Action Refactoring | ⚠️ Partial | Entity actions yes, ACL actions no |
| Handler Refactoring | ⚠️ Partial | Entity postgres yes, ACL postgres no |
| **Access Control System** | ❌ No | Must exclude |
| SharePoint 2019 V2 Source | ❌ No | Tightly coupled to ACL |

---

## 🟢 SAFE TO MERGE: Vespa & Embedding Improvements

### 1. VespaChunkEmbedProcessor (NEW)
**File:** `backend/airweave/platform/sync/processors/vespa_chunk_embed.py` (+336 lines)

New processor for Vespa's entity-as-document model:
- Keeps original entity (1:1 mapping, not 1:N like Qdrant)
- Stores chunks + embeddings as arrays in `entity.vespa_content`
- Uses 768-dim embeddings for ranking + 96 int8 binary-packed for ANN

**Depends on:**
- `VespaContent` model in `_base.py` (safe)

---

### 2. Processor Rename: ChunkEmbedProcessor → QdrantChunkEmbedProcessor
**File:** `backend/airweave/platform/sync/processors/qdrant_chunk_embed.py` (renamed)

Just a rename to clarify that the existing processor is Qdrant-specific. No functional changes.

---

### 3. Matryoshka Embeddings Support
**File:** `backend/airweave/platform/embedders/openai.py` (+116 lines)

Added support for OpenAI's Matryoshka dimension reduction:
- New `dimensions` parameter in `embed_many()`
- Allows requesting 768-dim or other sizes from text-embedding-3-large
- Context parameter now accepts `SyncContext`, `ContextualLogger`, or `None`

---

### 4. VespaContent Model
**File:** `backend/airweave/platform/entities/_base.py` (+46 lines for VespaContent only)

New Pydantic model for Vespa's entity-as-document storage:
```python
class VespaContent(BaseModel):
    chunks: List[str]
    chunk_small_embeddings: List[List[int]]   # 96 int8 binary-packed
    chunk_large_embeddings: List[List[float]] # 768-dim for ranking
```

**⚠️ Note:** This file also contains `AccessControl` model - you'll need to cherry-pick only `VespaContent`.

---

### 5. Vespa Destination Improvements
**File:** `backend/airweave/platform/destinations/vespa.py` (+589 lines)

Major improvements to the Vespa destination:
- Updated to use external embeddings from `VespaChunkEmbedProcessor`
- New schema fields for chunks and embeddings
- Improved search with provided embeddings and dynamic rerank
- Faster async deletion

**⚠️ Contains some ACL-related code** - need to review and exclude ACL parts.

---

### 6. Search Operations Debug Logging
**Files in** `backend/airweave/search/operations/`:
- `embed_query.py` (+27 lines) - debug logging
- `reranking.py` (+39 lines) - debug logging
- `retrieval.py` (+36 lines) - debug logging
- `query_expansion.py` (+24 lines) - debug logging
- `generate_answer.py` (+41 lines) - debug logging
- `user_filter.py` (+76 lines) - debug logging

General improvements to search operation logging - all safe to merge.

---

### 7. Vespa Schema Updates
**File:** `vespa/app/schemas/base_entity.sd` (+51/-51 lines)
**File:** `vespa/app.zip` (binary)

Updated Vespa schema for direct tensor assignment with external embeddings.

---

## 🟡 PARTIAL MERGE: Sync Action/Handler Refactoring

The sync actions and handlers were refactored into a cleaner structure. You can merge the entity-specific parts but must exclude access control parts.

### Sync Actions Refactoring

**Can merge:**
- `backend/airweave/platform/sync/actions/__init__.py` (partial - entity imports only)
- `backend/airweave/platform/sync/actions/entity/__init__.py` (NEW)
- `backend/airweave/platform/sync/actions/entity/builder.py` (NEW - moved from root)
- `backend/airweave/platform/sync/actions/entity/dispatcher.py` (moved)
- `backend/airweave/platform/sync/actions/entity/resolver.py` (moved)
- `backend/airweave/platform/sync/actions/entity/types.py` (NEW)

**Must exclude:**
- `backend/airweave/platform/sync/actions/access_control/` (entire directory)
- `backend/airweave/platform/sync/actions/access_control/__init__.py`
- `backend/airweave/platform/sync/actions/access_control/dispatcher.py`
- `backend/airweave/platform/sync/actions/access_control/resolver.py`
- `backend/airweave/platform/sync/actions/access_control/types.py`

### Handler Refactoring

**Can merge:**
- `backend/airweave/platform/sync/handlers/__init__.py` (partial)
- `backend/airweave/platform/sync/handlers/entity_postgres.py` (renamed from `postgres.py`)
- `backend/airweave/platform/sync/handlers/protocol.py` (partial - entity parts)

**Must exclude:**
- `backend/airweave/platform/sync/handlers/access_control_postgres.py` (NEW - 155 lines)

---

## 🔴 MUST EXCLUDE: Access Control System

These files implement the access control feature and must NOT be merged to `poc/vespa`.

### Database Layer
- `backend/airweave/crud/crud_access_control_membership.py` (149 lines) - NEW
- `backend/airweave/models/access_control_membership.py` (69 lines) - NEW
- `backend/airweave/schemas/access_control.py` (32 lines) - NEW

### Migrations
- `alembic/versions/..._add_access_control_membership_table.py` (77 lines)
- `alembic/versions/..._add_supports_access_control_to_source.py` (41 lines)

### Platform Module
- `backend/airweave/platform/access_control/` (entire directory)
  - `__init__.py` (6 lines)
  - `broker.py` (262 lines) - core ACL logic
  - `schemas.py` (58 lines)

### Source Modifications
- `backend/airweave/models/source.py` (+3 lines) - `supports_access_control` field
- `backend/airweave/schemas/source.py` (+8 lines) - ACL schema additions

### Sync Pipeline
- `backend/airweave/platform/sync/access_control_pipeline.py` (59 lines) - NEW
- `backend/airweave/platform/sync/orchestrator.py` (69 lines) - orchestrates entity + ACL pipelines

### Search Operations
- `backend/airweave/search/operations/access_control_filter.py` (167 lines) - NEW
- Parts of `backend/airweave/search/factory.py` that add ACL filter to pipeline

### SharePoint 2019 V2 Source (tightly coupled to ACL)
- `backend/airweave/platform/sources/sharepoint2019v2/` (entire directory)
  - `__init__.py` (14 lines)
  - `source.py` (547 lines)
  - `client.py` (324 lines)
  - `builders.py` (352 lines)
  - `acl.py` (223 lines) - ACL-specific
  - `ldap.py` (306 lines) - LDAP integration for ACL
- `backend/airweave/platform/entities/sharepoint2019v2.py` (115 lines)

---

## Commit-by-Commit Breakdown

Here are the commits from oldest to newest, classified by mergeability:

| Commit | Message | Merge? |
|--------|---------|:------:|
| `f92ed634` | feat: add access control membership database layer | ❌ |
| `1f6d491a` | feat: add access control core module and source support | ❌ |
| `28a43486` | refactor: add generic handler/dispatcher architecture for access control | ⚠️ Partial |
| `434791bd` | feat: add access control support to Vespa destination | ❌ |
| `fe33275b` | feat: add access control filter to search pipeline | ❌ |
| `4c120e06` | feat: port SharePoint 2019 V2 source with access control support | ❌ |
| `0211c13a` | docs: add access control integration overview and implementation plan | ❌ |
| `edd6a36f` | feat: quicker asynchronuous vespa deletion | ✅ |
| `019c8d01` | feat: add VespaContent model for entity-as-document architecture | ⚠️ (exclude AccessControl) |
| `a7db285e` | feat: add Matryoshka dimensions support to DenseEmbedder | ✅ |
| `26119aa2` | feat: add VespaChunkEmbedProcessor for external chunking/embedding | ✅ |
| `cc6575bb` | refactor: rename ChunkEmbedProcessor to QdrantChunkEmbedProcessor | ✅ |
| `fcaf9e36` | feat: add VESPA_CHUNKS_AND_EMBEDDINGS processing requirement | ✅ |
| `2038a69e` | refactor: update VespaDestination to use external embeddings | ✅ |
| `d347c5af` | refactor: update Vespa schema for direct tensor assignment | ✅ |
| `56d901ce` | chore: remove hugging-face-embedder from Vespa services | ✅ |
| `a574c732` | docs: clarify resolve phase includes bulk DB lookup | ✅ |
| `c571f42d` | docs: update overview with new processor names | ✅ |
| `ce12a905` | Merge branch 'poc/vespa' into feat/merge-sharepoint-vespa | ✅ |
| `d0b81c49` | refactor: sync action handling | ⚠️ Partial |
| `454ffbf8` | fix: remove unused HandlerContext | ✅ |
| `5e129bc6` | refactor: entity action imports | ⚠️ Partial |
| `536a0714` | fix: chunk and embedding fields need to be inside the schema | ✅ |
| `276f2194` | feat(providers): add Matryoshka dimension support to embed method | ✅ |
| `adb8902e` | feat(search): use destination-aware embedding dimensions in EmbedQuery | ✅ |
| `0b438cc7` | feat(vespa): optimize search with provided embeddings and dynamic rerank | ✅ |
| `0b108086` | feat(search): add comprehensive debug logging to search operations | ✅ |
| `cfe6c9d7` | feat(vespa): improve chunk embed processor logging | ✅ |
| `f31dd903` | chore(vespa): update app.zip with latest schema | ✅ |

---

## Recommended Merge Strategy

### Option 1: Cherry-pick Safe Commits
Cherry-pick the ✅ commits individually, skipping ❌ commits entirely.

```bash
git checkout poc/vespa
git cherry-pick edd6a36f  # vespa deletion
git cherry-pick a7db285e  # Matryoshka embeddings
git cherry-pick 26119aa2  # VespaChunkEmbedProcessor
git cherry-pick cc6575bb  # rename to QdrantChunkEmbedProcessor
# ... continue with ✅ commits
```

### Option 2: Merge with Manual Exclusions
Merge the branch and then revert/remove ACL-related changes:

```bash
git checkout poc/vespa
git merge feat/merge-sharepoint-vespa --no-commit
# Manually revert ACL files
git checkout HEAD -- backend/airweave/platform/access_control/
git checkout HEAD -- backend/airweave/crud/crud_access_control_membership.py
# ... etc
git commit
```

### Option 3: Create Patch Files
Create patches for only the safe changes and apply them.

---

## Files That Need Careful Review

These files have both safe changes AND ACL changes mixed together:

1. **`backend/airweave/platform/entities/_base.py`**
   - ✅ Add `VespaContent` model
   - ✅ Add `vespa_content` field to `BaseEntity`
   - ❌ Add `AccessControl` model
   - ❌ Add `access` field to `BaseEntity`

2. **`backend/airweave/platform/destinations/vespa.py`**
   - ✅ External embedding support
   - ✅ Improved deletion
   - ❌ ACL field handling (check for `access_control`, `viewers`, etc.)

3. **`backend/airweave/platform/sync/handlers/__init__.py`**
   - ✅ Entity handler exports
   - ❌ AccessControlPostgresHandler export

4. **`backend/airweave/search/factory.py`**
   - ✅ General improvements
   - ❌ AccessControlFilter addition

5. **`backend/airweave/platform/sync/actions/__init__.py`**
   - ✅ Entity action exports
   - ❌ AccessControl action exports
