#!/usr/bin/env python3
"""Test if transformer removes control characters - simpler approach."""

import sys
import os

# Set minimal env vars
os.environ.setdefault("FIRST_SUPERUSER", "test@test.com")
os.environ.setdefault("FIRST_SUPERUSER_PASSWORD", "test")
os.environ.setdefault("ENCRYPTION_KEY", "test" * 8)
os.environ.setdefault("STATE_SECRET", "test" * 8)
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")

from uuid import uuid4
from airweave.platform.destinations.vespa.transformer import EntityTransformer
from unittest.mock import MagicMock

print("=" * 60)
print("Testing Vespa Transformer Control Character Handling")
print("=" * 60)
print()

# Create a mock entity with control characters
test_text = "Hello\x0bWorld\x01Test\x00End"
print(f"1. Input text with control characters:")
print(f"   Text: {repr(test_text)}")
control_chars = [
    (i, hex(ord(c))) for i, c in enumerate(test_text) if ord(c) < 32 and c not in "\n\r\t"
]
print(f"   Control chars: {control_chars}")
print()

# Create minimal mock entity
entity = MagicMock()
entity.entity_id = "test-entity-123"
entity.name = "Test Entity"
entity.textual_representation = test_text
entity.breadcrumbs = None
entity.created_at = None
entity.updated_at = None
entity.__class__.__name__ = "BaseEntity"

# Mock system metadata
entity.airweave_system_metadata = MagicMock()
entity.airweave_system_metadata.entity_type = "BaseEntity"
entity.airweave_system_metadata.sync_id = str(uuid4())
entity.airweave_system_metadata.sync_job_id = str(uuid4())
entity.airweave_system_metadata.hash = "test-hash"
entity.airweave_system_metadata.original_entity_id = None
entity.airweave_system_metadata.source_name = None
entity.airweave_system_metadata.chunk_index = None
entity.airweave_system_metadata.dense_embedding = None
entity.airweave_system_metadata.sparse_embedding = None

# Make isinstance() work
entity.__class__.__bases__ = (object,)

# Transform it
print(f"2. Transforming with EntityTransformer:")
transformer = EntityTransformer(collection_id=uuid4())

try:
    doc = transformer.transform(entity)

    # Check the output
    output_text = doc.fields.get("textual_representation", "")
    print(f"   Transformed successfully")
    print(f"   Output text: {repr(output_text)}")
    print()

    output_control_chars = [
        (i, hex(ord(c))) for i, c in enumerate(output_text) if ord(c) < 32 and c not in "\n\r\t"
    ]
    print(f"3. Checking output:")
    print(f"   Control chars in output: {output_control_chars}")
    print()

    # Verdict
    print("=" * 60)
    if output_control_chars:
        print("❌ FAIL: Control characters still present!")
        print(f"   Vespa will reject with 'illegal code point' error")
        print(f"   First problematic char: {output_control_chars[0]}")
        success = False
    else:
        print("✅ SUCCESS: Control characters removed!")
        print(f"   Vespa will accept this document")
        success = True
    print("=" * 60)

    sys.exit(0 if success else 1)

except Exception as e:
    print(f"❌ Error during transformation: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
