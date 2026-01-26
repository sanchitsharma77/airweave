#!/usr/bin/env python3
"""Test actual transformer implementation from codebase."""

import sys
import os

# Set minimal env vars to avoid Settings validation errors
os.environ.setdefault("FIRST_SUPERUSER", "test@test.com")
os.environ.setdefault("FIRST_SUPERUSER_PASSWORD", "test")
os.environ.setdefault("ENCRYPTION_KEY", "test" * 8)
os.environ.setdefault("STATE_SECRET", "test" * 8)
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")

try:
    from airweave.platform.destinations.vespa import transformer

    # Check if sanitization function exists
    has_sanitize = hasattr(transformer, "_sanitize_for_vespa")

    print("=" * 60)
    print("Checking transformer.py for sanitization fix")
    print("=" * 60)
    print()
    print(f"Module: {transformer.__file__}")
    print(f"Has _sanitize_for_vespa function: {has_sanitize}")
    print()

    if has_sanitize:
        print("✅ FIX IS PRESENT")
        print()
        # Test it
        sanitize = transformer._sanitize_for_vespa
        test_input = "Hello\x0bWorld\x01Test"
        result = sanitize(test_input)
        print(f"Test: {repr(test_input)} -> {repr(result)}")

        if result == "HelloWorldTest":
            print("✅ Sanitization working correctly!")
        else:
            print(f"❌ Sanitization not working! Expected 'HelloWorldTest', got {repr(result)}")
    else:
        print("❌ FIX IS NOT PRESENT")
        print("   The _sanitize_for_vespa function does not exist.")
        print("   Vespa will reject entities with control characters.")

    print()
    print("=" * 60)

except Exception as e:
    print(f"❌ Error importing: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
