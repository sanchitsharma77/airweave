#!/usr/bin/env python3
"""Search Vespa using the pyvespa Python API.

This script demonstrates how to search with verbose output showing:
- Query processing
- Matched candidates
- Ranking phases
- Match features and scores

Usage:
    python vespa_search.py "your search query"
    python vespa_search.py "visa application" --hits 10
    python vespa_search.py "airweave" --profile hybrid-linear
"""

import argparse
import json

from vespa.application import Vespa
from vespa.io import VespaQueryResponse


def create_vespa_client() -> Vespa:
    """Create a Vespa client connection."""
    return Vespa(url="http://localhost", port=8081)


def search_with_query_profile(
    app: Vespa,
    query: str,
    hits: int = 5,
    profile: str = "hybrid-rrf",
    summary: str = "no-chunks",
    verbose: bool = True,
) -> VespaQueryResponse:
    """Search using the predefined query profile.

    Args:
        app: Vespa application client
        query: Search query text
        hits: Number of results to return
        profile: Ranking profile (hybrid-rrf or hybrid-linear)
        summary: Document summary to use (no-chunks or top_3_chunks)
        verbose: Whether to print detailed output
    """
    if verbose:
        print(f"\n{'=' * 70}")
        print(f"SEARCH QUERY: '{query}'")
        print(f"{'=' * 70}")
        print(f"  Profile: {profile}")
        print(f"  Hits: {hits}")
        print(f"  Summary: {summary}")

    # Use query profile - this sets up embeddings and YQL automatically
    response = app.query(
        query=query,
        queryProfile="hybrid",
        hits=hits,
        **{
            "ranking.profile": profile,
            "presentation.summary": summary,
            "presentation.timing": True,
            # Request match features for debugging
            "ranking.listFeatures": True,
        },
    )

    return response


def search_with_explicit_yql(
    app: Vespa,
    query: str,
    hits: int = 5,
    profile: str = "hybrid-rrf",
    verbose: bool = True,
) -> VespaQueryResponse:
    """Search with explicit YQL for full control and visibility.

    This shows exactly what the query profile does under the hood.
    """
    if verbose:
        print(f"\n{'=' * 70}")
        print(f"EXPLICIT YQL SEARCH: '{query}'")
        print(f"{'=' * 70}")

    # Build the YQL query explicitly
    yql = """
        select * from base_entity 
        where ({targetHits:30}userInput(@query)) or
              ({targetHits:30}nearestNeighbor(chunk_small_embeddings, embedding))
    """

    if verbose:
        print(f"  YQL: {yql.strip()}")

    response = app.query(
        yql=yql,
        query=query,
        hits=hits,
        **{
            "ranking.profile": profile,
            "ranking.features.query(embedding)": f'embed(nomicmb, "{query}")',
            "ranking.features.query(float_embedding)": f'embed(nomicmb, "{query}")',
            "presentation.timing": True,
            "ranking.listFeatures": True,
        },
    )

    return response


def print_search_results(response: VespaQueryResponse, verbose: bool = True):
    """Print search results with detailed information."""
    print(f"\n{'=' * 70}")
    print("SEARCH RESULTS")
    print(f"{'=' * 70}")

    # Response metadata
    json_response = response.json
    root = json_response.get("root", {})

    print("\n📊 METADATA:")
    print(f"  Total Matches: {root.get('fields', {}).get('totalCount', 'N/A')}")

    # Timing info
    timing = json_response.get("timing", {})
    if timing:
        print("\n⏱️  TIMING:")
        print(f"  Query Time: {timing.get('querytime', 'N/A')}s")
        print(f"  Summary Time: {timing.get('summaryfetchtime', 'N/A')}s")
        print(f"  Search Time: {timing.get('searchtime', 'N/A')}s")

    # Check for errors
    errors = root.get("errors", [])
    if errors:
        print("\n❌ ERRORS:")
        for error in errors:
            print(f"  - [{error.get('code')}] {error.get('message')}")
        return

    # Results
    children = root.get("children", [])
    print(f"\n📄 HITS: {len(children)} documents returned")

    for i, hit in enumerate(children, 1):
        print(f"\n{'─' * 60}")
        print(f"HIT #{i}")
        print(f"{'─' * 60}")

        # Basic info
        fields = hit.get("fields", {})
        print(f"  📌 Document ID: {hit.get('id', 'N/A')}")
        print(f"  📝 Name: {fields.get('name', 'N/A')}")
        print(f"  🆔 Entity ID: {fields.get('entity_id', 'N/A')}")
        print(f"  ⭐ Relevance Score: {hit.get('relevance', 'N/A')}")

        # Breadcrumbs
        breadcrumbs = fields.get("breadcrumbs", [])
        if breadcrumbs:
            print(f"  🧭 Breadcrumbs: {' → '.join([b.get('name', '?') for b in breadcrumbs])}")

        # Timestamps
        created = fields.get("created_at")
        updated = fields.get("updated_at")
        if created:
            print(f"  📅 Created: {created}")
        if updated:
            print(f"  📅 Updated: {updated}")

        # Match features (ranking signals)
        match_features = hit.get("matchfeatures", {}) or hit.get("fields", {}).get(
            "matchfeatures", {}
        )
        if match_features and verbose:
            print("\n  📈 MATCH FEATURES (Ranking Signals):")
            for feature, value in sorted(match_features.items()):
                if isinstance(value, float):
                    print(f"      {feature}: {value:.6f}")
                else:
                    print(f"      {feature}: {value}")

        # Summary features
        summary_features = hit.get("summaryfeatures", {}) or fields.get("summaryfeatures", {})
        if summary_features and verbose:
            print("\n  📊 SUMMARY FEATURES:")
            for feature, value in sorted(summary_features.items()):
                print(f"      {feature}: {value}")

        # Chunks (if using top_3_chunks summary)
        chunks = fields.get("chunks_top3", [])
        if chunks:
            print(f"\n  📄 TOP CHUNKS ({len(chunks)}):")
            for j, chunk in enumerate(chunks, 1):
                preview = chunk[:100] + "..." if len(chunk) > 100 else chunk
                print(f"      [{j}] {preview}")


def search_lexical_only(app: Vespa, query: str, hits: int = 5) -> VespaQueryResponse:
    """Lexical-only search (BM25) for comparison."""
    print(f"\n{'=' * 70}")
    print(f"LEXICAL-ONLY SEARCH: '{query}'")
    print(f"{'=' * 70}")

    response = app.query(
        yql=f'select * from base_entity where default contains "{query}"',
        hits=hits,
        **{
            "ranking.profile": "default",
            "presentation.timing": True,
        },
    )
    return response


def count_documents(app: Vespa) -> int:
    """Count total documents in the index."""
    response = app.query(
        yql="select * from base_entity where true limit 0",
        hits=0,
    )
    return response.json.get("root", {}).get("fields", {}).get("totalCount", 0)


def main():
    parser = argparse.ArgumentParser(description="Search Vespa with verbose output")
    parser.add_argument("query", nargs="?", default="visa application", help="Search query")
    parser.add_argument("--hits", type=int, default=5, help="Number of results")
    parser.add_argument("--profile", choices=["hybrid-rrf", "hybrid-linear"], default="hybrid-rrf")
    parser.add_argument("--summary", choices=["no-chunks", "top_3_chunks"], default="no-chunks")
    parser.add_argument("--lexical", action="store_true", help="Use lexical-only search")
    parser.add_argument(
        "--explicit", action="store_true", help="Use explicit YQL instead of query profile"
    )
    parser.add_argument("--quiet", action="store_true", help="Less verbose output")
    args = parser.parse_args()

    # Create client
    app = create_vespa_client()

    # Test connection and show document count
    print(f"Connecting to Vespa at {app.url}:{app.port}...")
    try:
        doc_count = count_documents(app)
        print(f"Connected! Index contains {doc_count} documents.")
    except Exception as e:
        print(f"Failed to connect: {e}")
        return

    # Execute search
    if args.lexical:
        response = search_lexical_only(app, args.query, args.hits)
    elif args.explicit:
        response = search_with_explicit_yql(
            app, args.query, args.hits, args.profile, verbose=not args.quiet
        )
    else:
        response = search_with_query_profile(
            app, args.query, args.hits, args.profile, args.summary, verbose=not args.quiet
        )

    # Print results
    print_search_results(response, verbose=not args.quiet)

    # Raw JSON for debugging
    if not args.quiet:
        print(f"\n{'=' * 70}")
        print("RAW JSON RESPONSE (first 2000 chars)")
        print(f"{'=' * 70}")
        raw = json.dumps(response.json, indent=2)
        print(raw[:2000] + ("..." if len(raw) > 2000 else ""))


if __name__ == "__main__":
    main()
