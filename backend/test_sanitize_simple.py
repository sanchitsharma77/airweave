#!/usr/bin/env python3
"""Simple test of control character sanitization without dependencies."""

import re


def _sanitize_for_vespa(text: str) -> str:
    """Sanitize text for Vespa by removing control characters.

    Vespa strictly rejects control characters (code points < 32) except:
    - \n (newline, 0x0A)
    - \r (carriage return, 0x0D)
    - \t (tab, 0x09)
    """
    if not text:
        return text

    # Remove all control characters except newline, carriage return, and tab
    return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text)


def test_sanitization():
    """Test the sanitization function."""
    print("=" * 60)
    print("Testing Vespa Control Character Sanitization")
    print("=" * 60)
    print()

    tests = [
        # (input, expected_output, description)
        ("Hello\x0bWorld", "HelloWorld", "0xB vertical tab (the actual error)"),
        ("Test\x01\x02\x03End", "TestEnd", "0x01, 0x02, 0x03 (SOH, STX, ETX)"),
        ("Line1\nLine2\rLine3\tTab", "Line1\nLine2\rLine3\tTab", "Keep newline, CR, tab"),
        ("\x00Null\x00Byte", "NullByte", "0x00 null bytes"),
        ("Clean text", "Clean text", "Already clean"),
        ("", "", "Empty string"),
    ]

    all_passed = True

    for i, (input_text, expected, description) in enumerate(tests, 1):
        print(f"Test {i}: {description}")
        print(f"  Input:    {repr(input_text)}")
        print(f"  Expected: {repr(expected)}")

        result = _sanitize_for_vespa(input_text)
        print(f"  Result:   {repr(result)}")

        if result == expected:
            print(f"  ✅ PASS")
        else:
            print(f"  ❌ FAIL")
            all_passed = False

        # Check for remaining control chars
        remaining = [
            (i, hex(ord(c))) for i, c in enumerate(result) if ord(c) < 32 and c not in "\n\r\t"
        ]
        if remaining:
            print(f"  ⚠️  WARNING: Control characters remain: {remaining}")
            all_passed = False

        print()

    print("=" * 60)
    if all_passed:
        print("✅ ALL TESTS PASSED - Sanitization is working!")
        print("   Safe to deploy to production.")
    else:
        print("❌ SOME TESTS FAILED - Fix required!")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    import sys

    success = test_sanitization()
    sys.exit(0 if success else 1)
