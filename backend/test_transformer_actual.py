#!/usr/bin/env python3
"""Test if transformer actually removes control characters from documents."""

import sys
import os
from datetime import datetime, timezone

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
from airweave.platform.entities._base import AirweaveSystemMetadata
from airweave.platform.entities.google_drive import GoogleDriveFileEntity

print("=" * 60)
print("Testing Vespa Transformer Control Character Handling")
print("=" * 60)
print()

# Create a test entity with control characters (including 0xB that causes the error)
test_text = "Hello\x0bWorld\x01Test\x00End"
print(f"1. Creating entity with control characters:")
print(f"   Text: {repr(test_text)}")
control_chars = [
    (i, hex(ord(c))) for i, c in enumerate(test_text) if ord(c) < 32 and c not in "\n\r\t"
]
print(f"   Control chars: {control_chars}")
print()

# Create entity (using GoogleDriveFileEntity like the actual error)
entity = GoogleDriveFileEntity(
    gid="test-gid-123",
    name="Test File",
    textual_representation=test_text,
    url="https://drive.google.com/test",
    size=1000,
    file_type="application/pdf",
    airweave_system_metadata=AirweaveSystemMetadata(
        entity_type="GoogleDriveFileEntity",
        sync_id=uuid4(),
        sync_job_id=uuid4(),
        hash="test-hash",
    ),
)

# Transform it
print(f"2. Transforming entity with EntityTransformer:")
transformer = EntityTransformer(collection_id=uuid4())
doc = transformer.transform(entity)
print(f"   Document ID: {doc.id}")
print(f"   Document schema: {doc.schema}")
print()

# Check the output
output_text = doc.fields.get("textual_representation", "")
print(f"3. Checking transformed output:")
print(f"   Output text: {repr(output_text)}")

output_control_chars = [
    (i, hex(ord(c))) for i, c in enumerate(output_text) if ord(c) < 32 and c not in "\n\r\t"
]
print(f"   Control chars in output: {output_control_chars}")
print()

# Verdict
print("=" * 60)
if output_control_chars:
    print("❌ FAIL: Control characters still present!")
    print(f"   This will cause Vespa to reject with 'illegal code point' error")
    print(f"   First error would be: {output_control_chars[0]}")
    success = False
else:
    print("✅ SUCCESS: Control characters removed!")
    print(f"   Vespa will accept this document")
    success = True
print("=" * 60)

sys.exit(0 if success else 1)
