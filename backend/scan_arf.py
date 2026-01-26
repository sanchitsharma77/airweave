#!/usr/bin/env python3
"""Scan ARF entities for control characters."""

import json
import sys
from pathlib import Path

sync_id = "c67da7fd-5c57-4c7b-8ba2-d716d296e72a"
base_path = Path(__file__).parent / "local_storage" / "raw" / sync_id
entities_dir = base_path / "entities"

print(f"📂 Scanning: {entities_dir}")
print(f"   Exists: {entities_dir.exists()}\n")

if not entities_dir.exists():
    sys.exit(1)

entity_files = list(entities_dir.glob("*.json"))
print(f"Found {len(entity_files)} entity files\n")

issues_found = 0
entities_checked = 0

for entity_file in entity_files:  # Check all entities
    entities_checked += 1

    # Progress update every 50 entities
    if entities_checked % 50 == 0:
        print(f"Checked {entities_checked}/{len(entity_files)} entities...", end="\r")

    try:
        with open(entity_file, "r", encoding="utf-8") as f:
            entity_dict = json.load(f)

        text_repr = entity_dict.get("textual_representation", "")
        if not text_repr:
            continue

        # Check for control characters (excluding newline, carriage return, tab)
        control_chars = [
            (i, hex(ord(c))) for i, c in enumerate(text_repr) if ord(c) < 32 and c not in "\n\r\t"
        ]

        if control_chars:
            issues_found += 1
            entity_id = entity_dict.get("entity_id", entity_file.stem)
            entity_class = entity_dict.get("__entity_class__", "Unknown")

            print(f"🚨 ISSUE #{issues_found}")
            print(f"   File: {entity_file.name}")
            print(f"   Entity ID: {entity_id}")
            print(f"   Entity class: {entity_class}")
            print(f"   Text length: {len(text_repr)}")
            print(f"   Control chars: {len(control_chars)}")
            print(f"   First 5 positions: {control_chars[:5]}")
            print(f"   Text preview: {repr(text_repr[:100])}")
            print()

            if issues_found >= 10:
                print(f"\n... stopping detailed output after 10 examples (continuing scan)")

    except Exception as e:
        print(f"⚠️  Error reading {entity_file.name}: {e}")

print(f"\n\n{'=' * 60}")
print(f"📊 SCAN COMPLETE")
print(f"{'=' * 60}")
print(f"Total entities checked: {entities_checked}")
print(f"Entities with control characters: {issues_found}")
if issues_found == 0:
    print("✅ No control character issues found!")
else:
    print(f"⚠️  {issues_found}/{entities_checked} entities have control characters")
    print(f"   ({100 * issues_found / entities_checked:.1f}% of total)")
