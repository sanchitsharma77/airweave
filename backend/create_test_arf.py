#!/usr/bin/env python3
"""Create a minimal ARF snapshot with control characters for testing."""

import json
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

# Create test sync directory
sync_id = "test-control-chars-sync"
arf_dir = Path(__file__).parent / "local_storage" / "raw" / sync_id
entities_dir = arf_dir / "entities"
entities_dir.mkdir(parents=True, exist_ok=True)

print(f"Creating test ARF at: {arf_dir}")

# Create manifest
manifest = {
    "sync_id": sync_id,
    "source_short_name": "test",
    "collection_id": str(uuid4()),
    "collection_readable_id": "test-control-chars",
    "organization_id": str(uuid4()),
    "created_at": datetime.now(timezone.utc).isoformat(),
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "sync_jobs": [str(uuid4())],
    "vector_size": 3072,
    "embedding_model_name": "text-embedding-3-large",
}

manifest_file = arf_dir / "manifest.json"
with open(manifest_file, "w") as f:
    json.dump(manifest, f, indent=2)
print(f"✓ Created manifest.json")

# Create test entity with control characters in textual_representation
# Use LinearIssueEntity - simpler, no file dependencies
test_text = "This is a test issue description.\n\nIt has normal content.\x0bBut here's a vertical tab (0xB).\x01And here's SOH (0x01).\x00And a null byte.\n\nVespa will reject this!"

entity = {
    "__entity_class__": "LinearIssueEntity",
    "__entity_module__": "airweave.platform.entities.linear",
    "__captured_at__": datetime.now(timezone.utc).isoformat(),
    # Required fields for LinearIssueEntity
    "gid": "test-linear-issue-control-chars",
    "identifier": "TEST-123",
    "issue_id": "TEST-123",
    "title": "Test Issue With Control Chars",
    "description": test_text,
    "textual_representation": test_text,
    "breadcrumbs": [],
    "url": "https://linear.app/test/issue/TEST-123",
    "status": "In Progress",
    "priority": 1,
    "created_time": datetime.now(timezone.utc).isoformat(),
    "updated_time": datetime.now(timezone.utc).isoformat(),
    "created_at": datetime.now(timezone.utc).isoformat(),
    "updated_at": datetime.now(timezone.utc).isoformat(),
}

entity_file = entities_dir / "test-linear-issue-control-chars.json"
with open(entity_file, "w") as f:
    json.dump(entity, f, indent=2)
print(f"✓ Created entity: {entity_file.name}")

# Verify control characters
control_chars = [
    (i, hex(ord(c))) for i, c in enumerate(test_text) if ord(c) < 32 and c not in "\n\r\t"
]
print(f"\n✓ Entity has {len(control_chars)} control characters:")
for pos, code in control_chars[:5]:
    print(f"  Position {pos}: {code}")

print(f"\n{'=' * 60}")
print(f"✅ Test ARF created at:")
print(f"   {arf_dir}")
print(f"\nTo test with snapshot source, use path:")
print(f"   {arf_dir}")
print(f"{'=' * 60}")
