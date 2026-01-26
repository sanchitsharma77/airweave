#!/usr/bin/env python3
"""Create a test ARF with ASCII control chars AND Unicode noncharacters."""

import json
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

# Create test sync directory
sync_id = "test-unicode-nonchars"
arf_dir = Path(__file__).parent / "local_storage" / "raw" / sync_id
entities_dir = arf_dir / "entities"
entities_dir.mkdir(parents=True, exist_ok=True)

print(f"Creating test ARF at: {arf_dir}")

# Create manifest
manifest = {
    "sync_id": sync_id,
    "source_short_name": "test",
    "collection_id": str(uuid4()),
    "collection_readable_id": "test-unicode-nonchars",
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

# Create test entity with BOTH ASCII control chars AND Unicode noncharacters
test_text = (
    "This document has multiple illegal characters:\n\n"
    "ASCII control chars: \x0b (vertical tab), \x01 (SOH), \x00 (null)\n"
    "Unicode nonchars: \ufddc (the actual error from prod!), \ufdd0, \ufffe, \uffff\n"
    "Plus some high plane nonchars: \U0001fffe, \U0010ffff\n\n"
    "Vespa should reject all of these on main branch!"
)

entity = {
    "__entity_class__": "LinearIssueEntity",
    "__entity_module__": "airweave.platform.entities.linear",
    "__captured_at__": datetime.now(timezone.utc).isoformat(),
    # Required fields for LinearIssueEntity
    "gid": "test-unicode-nonchars",
    "identifier": "TEST-UNICODE",
    "issue_id": "TEST-UNICODE",
    "title": "Test Unicode Noncharacters",
    "description": test_text,
    "textual_representation": test_text,
    "breadcrumbs": [],
    "url": "https://linear.app/test/issue/TEST-UNICODE",
    "status": "In Progress",
    "priority": 1,
    "created_time": datetime.now(timezone.utc).isoformat(),
    "updated_time": datetime.now(timezone.utc).isoformat(),
    "created_at": datetime.now(timezone.utc).isoformat(),
    "updated_at": datetime.now(timezone.utc).isoformat(),
}

entity_file = entities_dir / "test-unicode-nonchars.json"
with open(entity_file, "w") as f:
    json.dump(entity, f, indent=2)
print(f"✓ Created entity: {entity_file.name}")

# Count all illegal characters
ascii_control = [
    (i, hex(ord(c))) for i, c in enumerate(test_text) if ord(c) < 32 and c not in "\n\r\t"
]
unicode_nonchars = [
    (i, hex(ord(c)))
    for i, c in enumerate(test_text)
    if 0xFDD0 <= ord(c) <= 0xFDEF or ord(c) in [0xFFFE, 0xFFFF] or ord(c) >= 0x1FFFE
]

print(f"\n✓ Entity has {len(ascii_control)} ASCII control chars:")
for pos, code in ascii_control[:5]:
    print(f"  Position {pos}: {code}")

print(f"\n✓ Entity has {len(unicode_nonchars)} Unicode noncharacters:")
for pos, code in unicode_nonchars[:10]:
    print(f"  Position {pos}: {code}")

print(f"\n{'=' * 60}")
print(f"✅ Test ARF created at:")
print(f"   {arf_dir}")
print(f"\nTo test with snapshot source, use path:")
print(f"   {arf_dir}")
print(f"\nExpected behavior:")
print(f"  Main branch (no fix): ❌ Vespa feed fails with 'illegal code point'")
print(f"  Fix branch:           ✅ All illegal chars removed, feed succeeds")
print(f"{'=' * 60}")
