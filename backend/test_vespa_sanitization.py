#!/usr/bin/env python3
"""Test Vespa control character sanitization on a specific entity."""

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from airweave.platform.destinations.vespa.transformer import EntityTransformer, _sanitize_for_vespa


async def test_entity(entity_id: str):
    """Test sanitization on a specific entity from ARF."""

    # Load entity from ARF
    arf_path = (
        Path(__file__).parent / "local_storage" / "raw" / "c67da7fd-5c57-4c7b-8ba2-d716d296e72a"
    )
    entity_file = arf_path / "entities" / f"{entity_id}.json"

    print(f"📂 Loading entity from: {entity_file}")

    if not entity_file.exists():
        print(f"❌ Entity file not found!")
        return False

    with open(entity_file, "r") as f:
        entity_dict = json.load(f)

    print(f"✓ Loaded {entity_dict.get('__entity_class__')}: {entity_dict.get('entity_id')}")

    # Test sanitization on textual_representation if present
    text = entity_dict.get("textual_representation", "")

    if text:
        print(f"\n📝 Testing sanitization on textual_representation:")
        print(f"   Original length: {len(text)}")

        # Check for control characters
        control_chars = [
            (i, hex(ord(c))) for i, c in enumerate(text) if ord(c) < 32 and c not in "\n\r\t"
        ]
        print(f"   Control characters found: {len(control_chars)}")
        if control_chars:
            print(f"   First 5: {control_chars[:5]}")

        # Test sanitization
        sanitized = _sanitize_for_vespa(text)
        print(f"   Sanitized length: {len(sanitized)}")
        print(f"   Characters removed: {len(text) - len(sanitized)}")

        # Verify no control chars remain
        remaining = [
            (i, hex(ord(c))) for i, c in enumerate(sanitized) if ord(c) < 32 and c not in "\n\r\t"
        ]
        if remaining:
            print(f"   ❌ FAILED: {len(remaining)} control characters remain!")
            print(f"   {remaining[:5]}")
            return False
        else:
            print(f"   ✅ SUCCESS: All control characters removed!")
    else:
        print(f"\n⚠️  No textual_representation in ARF (built during sync)")
        print(f"   This is normal - text is extracted from files during processing")

    # Simulate what happens during chunking
    print(f"\n🔧 Simulating transformer flow:")

    # Create a mock entity with problematic text
    test_text = "Hello\x0bWorld\x01Test\x00End"  # Contains 0xB, 0x01, 0x00
    print(f"   Test text with control chars: {repr(test_text)}")
    print(
        f"   Control chars: {[(i, hex(ord(c))) for i, c in enumerate(test_text) if ord(c) < 32 and c not in '\\n\\r\\t']}"
    )

    sanitized_test = _sanitize_for_vespa(test_text)
    print(f"   After sanitization: {repr(sanitized_test)}")
    print(f"   Expected: {repr('HelloWorldTestEnd')}")

    if sanitized_test == "HelloWorldTestEnd":
        print(f"   ✅ Sanitization working correctly!")
        return True
    else:
        print(f"   ❌ Sanitization failed!")
        return False


if __name__ == "__main__":
    entity_id = "18C3Rw8PwwOS-NVKygrLVJT8dw0sb-uNLdNy9eAmjLb4"

    print("=" * 60)
    print("Testing Vespa Control Character Sanitization")
    print("=" * 60)
    print()

    success = asyncio.run(test_entity(entity_id))

    print()
    print("=" * 60)
    if success:
        print("✅ SANITIZATION WORKING - Safe to sync")
    else:
        print("❌ SANITIZATION FAILED - Do not sync yet")
    print("=" * 60)

    sys.exit(0 if success else 1)
