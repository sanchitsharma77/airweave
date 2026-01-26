#!/usr/bin/env python3
"""Direct test of transformer._build_base_fields method."""

import sys, os

os.environ.update(
    {
        "FIRST_SUPERUSER": "test",
        "FIRST_SUPERUSER_PASSWORD": "test",
        "ENCRYPTION_KEY": "test" * 8,
        "STATE_SECRET": "test" * 8,
        "POSTGRES_HOST": "localhost",
        "POSTGRES_USER": "test",
        "POSTGRES_PASSWORD": "test",
    }
)

from uuid import uuid4
from airweave.platform.destinations.vespa.transformer import EntityTransformer
from types import SimpleNamespace

# Mock entity
entity = SimpleNamespace(
    entity_id="test-123",
    name="Test",
    textual_representation="Hello\x0bWorld\x01Test",  # Has 0xB and 0x01
    breadcrumbs=None,
    created_at=None,
    updated_at=None,
)

print("Input text:", repr(entity.textual_representation))
print(
    "Control chars:",
    [
        (i, hex(ord(c)))
        for i, c in enumerate(entity.textual_representation)
        if ord(c) < 32 and c not in "\n\r\t"
    ],
)

# Call the actual method
transformer = EntityTransformer(collection_id=uuid4())
fields = transformer._build_base_fields(entity)

output = fields.get("textual_representation", "")
print("\nOutput text:", repr(output))

control_out = [(i, hex(ord(c))) for i, c in enumerate(output) if ord(c) < 32 and c not in "\n\r\t"]
print("Control chars in output:", control_out)

if control_out:
    print("\n❌ FAIL - Control characters still present, Vespa will reject")
    sys.exit(1)
else:
    print("\n✅ SUCCESS - Control characters removed, Vespa will accept")
    sys.exit(0)
