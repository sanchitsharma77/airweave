#!/usr/bin/env python3
"""Test script for Vespa search via Airweave API.

Run with:
    python3 backend/airweave/vespa/scripts/test_api_search.py
"""

import json
import sys
import urllib.request


def test_search(collection_id: str = "vespa3-3yf1sj", query: str = "tasks to do"):
    """Test search endpoint."""
    url = f"http://localhost:8001/collections/{collection_id}/search"

    data = {
        "query": query,
        "limit": 5,
        "expand_query": False,
        "interpret_filters": False,
        "rerank": False,
        "generate_answer": False,
    }

    print(f"Searching collection '{collection_id}' for: '{query}'")
    print(f"URL: {url}")
    print()

    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            print("=== Search Results ===")
            if "results" in result:
                print(f"Got {len(result['results'])} results")
                print()
                for i, r in enumerate(result["results"][:5], 1):
                    payload = r.get("payload", r)
                    name = payload.get("name", "N/A")
                    score = r.get("score", 0)
                    entity_type = payload.get("entity_type", "?")
                    print(f"{i}. [{entity_type}] {name} (score: {score:.4f})")
                if result.get("completion"):
                    print(f"\nCompletion: {result['completion'][:200]}...")
            else:
                print(f"Response: {json.dumps(result, indent=2)[:1000]}")
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}")
        try:
            error_body = e.read().decode("utf-8")
            print(f"Error body: {error_body[:1000]}")
        except Exception:
            pass
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    collection = sys.argv[1] if len(sys.argv) > 1 else "vespa3-3yf1sj"
    query = sys.argv[2] if len(sys.argv) > 2 else "tasks to do"
    test_search(collection, query)
