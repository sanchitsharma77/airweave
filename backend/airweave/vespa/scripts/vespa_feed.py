#!/usr/bin/env python3
"""Feed documents to Vespa using the pyvespa Python API.

This script demonstrates how to feed documents with verbose output
showing exactly what Vespa is doing during indexing.

Usage:
    python vespa_feed.py [--limit N]
"""

import argparse
import json
import time
from pathlib import Path

from vespa.application import Vespa
from vespa.io import VespaResponse


def create_vespa_client() -> Vespa:
    """Create a Vespa client connection."""
    return Vespa(url="http://localhost", port=8081)


def feed_single_document(app: Vespa, doc: dict, verbose: bool = True) -> VespaResponse:
    """Feed a single document and show detailed response.

    Args:
        app: Vespa application client
        doc: Document in Vespa feed format {"put": "id:...", "fields": {...}}
        verbose: Whether to print detailed output
    """
    # Extract document ID from put path
    # Format: id:namespace:doctype::user_specified_id
    doc_id = doc["put"].split("::")[-1]
    fields = doc["fields"]

    if verbose:
        print(f"\n{'=' * 60}")
        print(f"FEEDING DOCUMENT: {doc_id}")
        print(f"{'=' * 60}")
        print(f"  Name: {fields.get('name', 'N/A')}")
        print(f"  Entity ID: {fields.get('entity_id', 'N/A')}")
        print(f"  Textual Rep Length: {len(fields.get('textual_representation', ''))}")
        print(f"  Payload Length: {len(fields.get('payload', ''))}")
        print(f"  Breadcrumbs: {len(fields.get('breadcrumbs', []))} items")

    start_time = time.time()

    # Feed the document
    # schema = document type, data_id = the unique ID within that type
    response = app.feed_data_point(
        schema="base_entity",
        data_id=doc_id,
        fields=fields,
    )

    elapsed = time.time() - start_time

    if verbose:
        print("\n  RESPONSE:")
        print(f"    Status: {response.status_code}")
        print(f"    Success: {response.is_successful()}")
        print(f"    Time: {elapsed:.3f}s")
        if hasattr(response, "json") and response.json:
            print(f"    Response body: {json.dumps(response.json, indent=6)}")
        if not response.is_successful():
            print(f"    ERROR: {response.get_json()}")

    return response


def feed_batch(app: Vespa, documents: list, verbose: bool = True) -> dict:
    """Feed multiple documents and return statistics.

    Args:
        app: Vespa application client
        documents: List of documents in Vespa feed format
        verbose: Whether to print detailed output
    """
    stats = {
        "total": len(documents),
        "success": 0,
        "failed": 0,
        "total_time": 0,
    }

    print(f"\n{'#' * 60}")
    print(f"STARTING BATCH FEED: {len(documents)} documents")
    print(f"{'#' * 60}")

    batch_start = time.time()

    for i, doc in enumerate(documents, 1):
        if verbose:
            print(f"\n[{i}/{len(documents)}]", end="")

        try:
            response = feed_single_document(app, doc, verbose=verbose)
            if response.is_successful():
                stats["success"] += 1
            else:
                stats["failed"] += 1
        except Exception as e:
            stats["failed"] += 1
            if verbose:
                print(f"  EXCEPTION: {e}")

    stats["total_time"] = time.time() - batch_start

    print(f"\n{'#' * 60}")
    print("BATCH FEED COMPLETE")
    print(f"{'#' * 60}")
    print(f"  Total: {stats['total']}")
    print(f"  Success: {stats['success']}")
    print(f"  Failed: {stats['failed']}")
    print(f"  Total Time: {stats['total_time']:.2f}s")
    print(f"  Avg Time/Doc: {stats['total_time'] / max(stats['total'], 1):.3f}s")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Feed documents to Vespa")
    parser.add_argument(
        "--limit", type=int, default=5, help="Number of documents to feed (default: 5)"
    )
    parser.add_argument("--all", action="store_true", help="Feed all documents")
    parser.add_argument("--quiet", action="store_true", help="Less verbose output")
    args = parser.parse_args()

    # Load the pre-transformed Vespa feed data
    feed_path = Path(__file__).parent.parent / "dataset" / "vespa_feed.json"
    print(f"Loading documents from: {feed_path}")

    with open(feed_path) as f:
        documents = json.load(f)

    print(f"Loaded {len(documents)} documents")

    # Limit if not feeding all
    if not args.all:
        documents = documents[: args.limit]
        print(f"Limiting to {len(documents)} documents (use --all to feed all)")

    # Create client and feed
    app = create_vespa_client()

    # Test connection
    print(f"\nConnecting to Vespa at {app.url}:{app.port}...")
    try:
        # Simple test query to verify connection
        test_response = app.query(yql="select * from base_entity where true", hits=0)
        doc_count = test_response.json.get("root", {}).get("fields", {}).get("totalCount", 0)
        print(f"Connected! Index contains {doc_count} documents.")
    except Exception as e:
        print(f"Failed to connect: {e}")
        return

    # Feed documents
    stats = feed_batch(app, documents, verbose=not args.quiet)

    print("\nDone! Documents are now searchable.")


if __name__ == "__main__":
    main()
