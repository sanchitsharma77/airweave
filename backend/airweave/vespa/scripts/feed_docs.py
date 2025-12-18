#!/usr/bin/env python3
"""Feed transformed documents to Vespa."""

import json
import sys
from pathlib import Path

import requests

VESPA_URL = "http://localhost:8081"


def feed_document(doc: dict) -> tuple[bool, str]:
    """Feed a single document to Vespa."""
    # Extract document ID from put path (e.g., "id:airweave:base_entity::12345")
    put_path = doc["put"]
    doc_id = put_path.split("::")[-1]

    url = f"{VESPA_URL}/document/v1/airweave/base_entity/docid/{doc_id}"
    payload = {"fields": doc["fields"]}

    try:
        response = requests.post(url, json=payload, timeout=60)
        if response.status_code == 200:
            return True, f"OK: {doc_id}"
        else:
            return False, f"FAIL: {doc_id} - {response.status_code}: {response.text[:200]}"
    except requests.Timeout:
        return False, f"TIMEOUT: {doc_id}"
    except Exception as e:
        return False, f"ERROR: {doc_id} - {str(e)}"


def main():
    feed_path = Path(__file__).parent.parent / "dataset" / "vespa_feed.json"

    if len(sys.argv) > 1:
        feed_path = Path(sys.argv[1])

    print(f"Reading from: {feed_path}")

    with open(feed_path) as f:
        documents = json.load(f)

    print(f"Feeding {len(documents)} documents...")

    success_count = 0
    fail_count = 0

    for i, doc in enumerate(documents, 1):
        success, message = feed_document(doc)
        if success:
            success_count += 1
            if i % 10 == 0:
                print(f"  Progress: {i}/{len(documents)}")
        else:
            fail_count += 1
            print(f"  {message}")

    print(f"\nDone! Success: {success_count}, Failed: {fail_count}")


if __name__ == "__main__":
    main()
