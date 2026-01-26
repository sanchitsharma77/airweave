#!/usr/bin/env python3
"""Test actual Vespa feed with control characters."""

import sys, os, asyncio

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
from airweave.platform.destinations.vespa.client import VespaClient
from airweave.core.config import settings
from types import SimpleNamespace


async def test_vespa_feed():
    print("=" * 60)
    print("Testing Actual Vespa Feed with Control Characters")
    print("=" * 60)
    print()

    # 1. Create entity with control characters
    test_text = "Hello\x0bWorld\x01Test\x00End"
    print(f"1. Creating test entity:")
    print(f"   Text: {repr(test_text)}")
    control_chars = [
        (i, hex(ord(c))) for i, c in enumerate(test_text) if ord(c) < 32 and c not in "\n\r\t"
    ]
    print(f"   Control chars: {control_chars}")
    print()

    entity = SimpleNamespace(
        entity_id="test-control-chars-123",
        name="Test Entity With Control Chars",
        textual_representation=test_text,
        breadcrumbs=None,
        created_at=None,
        updated_at=None,
        __class__=SimpleNamespace(__name__="BaseEntity"),
    )
    entity.airweave_system_metadata = SimpleNamespace(
        entity_type="BaseEntity",
        sync_id=str(uuid4()),
        sync_job_id=str(uuid4()),
        hash="test-hash",
        original_entity_id="test-control-chars-123",
        source_name="test",
        chunk_index=None,
        dense_embedding=None,
        sparse_embedding=None,
    )

    # 2. Transform to Vespa document
    print(f"2. Transforming to Vespa document:")
    collection_id = uuid4()
    transformer = EntityTransformer(collection_id=collection_id)
    doc = transformer.transform(entity)

    output_text = doc.fields.get("textual_representation", "")
    print(f"   Document ID: {doc.id}")
    print(f"   Schema: {doc.schema}")
    print(f"   Output text: {repr(output_text)}")

    output_control = [
        (i, hex(ord(c))) for i, c in enumerate(output_text) if ord(c) < 32 and c not in "\n\r\t"
    ]
    print(f"   Control chars in output: {output_control}")
    print()

    # 3. Try to feed to Vespa
    print(f"3. Feeding to Vespa ({settings.VESPA_URL}:{settings.VESPA_PORT}):")

    try:
        client = await VespaClient.connect()
        docs_by_schema = {doc.schema: [doc]}
        result = await client.feed_documents(docs_by_schema)

        print(f"   Feed result: {result.success_count} success, {len(result.failed_docs)} failed")
        print()

        if result.failed_docs:
            print("=" * 60)
            print("❌ VESPA REJECTED THE DOCUMENT")
            print("=" * 60)
            for doc_id, status, body in result.failed_docs:
                print(f"Document: {doc_id}")
                print(f"Status: {status}")
                print(f"Error: {body}")

                # Check if it's the control character error
                error_str = str(body)
                if (
                    "illegal code point" in error_str.lower()
                    or "could not parse" in error_str.lower()
                ):
                    print()
                    print("✓ Confirmed: Vespa rejected due to control characters")
                    print("  This is the expected behavior on main branch")
            print("=" * 60)
            return False
        else:
            print("=" * 60)
            print("✅ VESPA ACCEPTED THE DOCUMENT")
            print("=" * 60)
            print("The sanitization fix is working!")
            print("Control characters were removed before feeding")
            print("=" * 60)
            return True

    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_vespa_feed())
    sys.exit(0 if success else 1)
