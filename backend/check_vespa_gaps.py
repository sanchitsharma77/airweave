#!/usr/bin/env python3
"""Script to find syncs with Vespa gaps or ARF gaps.

Identifies syncs where:
1. Vespa document count is 0 or less than Postgres entity count
2. Postgres entity count is greater than ARF entity count

Run this script from a backend pod in production.

Usage:
    python check_vespa_gaps.py
"""

import asyncio
import os
import sys
from typing import Dict, List, Tuple
from uuid import UUID

import asyncpg


async def get_postgres_connection():
    """Establish PostgreSQL connection using environment variables."""
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    user = os.getenv("POSTGRES_USER", "airweave")
    password = os.getenv("POSTGRES_PASSWORD")
    database = os.getenv("POSTGRES_DB", "airweave")

    if not password:
        print("ERROR: POSTGRES_PASSWORD environment variable not set")
        sys.exit(1)

    try:
        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            timeout=30.0,
        )
        print(f"✓ Connected to PostgreSQL at {host}:{port}/{database}", flush=True)
        return conn
    except Exception as e:
        print(f"ERROR: Failed to connect to PostgreSQL: {e}")
        sys.exit(1)


async def get_all_syncs(conn) -> List[Dict]:
    """Get all non-orphaned syncs with collection info."""
    query = """
        SELECT s.id, sc.readable_collection_id
        FROM sync s
        INNER JOIN source_connection sc ON s.id = sc.sync_id
        ORDER BY s.created_at DESC
    """
    rows = await conn.fetch(query)
    return [{"sync_id": row["id"], "collection_id": row["readable_collection_id"]} for row in rows]


async def get_postgres_entity_count(conn, sync_id: UUID) -> int:
    """Get distinct entity count from PostgreSQL."""
    query = """
        SELECT COUNT(DISTINCT (entity_id, entity_definition_id))
        FROM entity
        WHERE sync_id = $1
    """
    result = await conn.fetchval(query, sync_id)
    return result or 0


async def get_arf_entity_count(sync_id: UUID) -> int:
    """Get entity count from ARF storage."""
    try:
        from airweave.platform.sync.arf.service import ArfService
        from airweave.platform.storage import storage_backend

        arf_service = ArfService(storage=storage_backend)
        count = await arf_service.get_entity_count(str(sync_id))
        return count
    except Exception:
        return 0


async def get_vespa_document_count(sync_id: UUID, collection_id: UUID) -> int:
    """Get document count from Vespa."""
    try:
        from airweave.platform.destinations.vespa import VespaDestination

        vespa = await VespaDestination.create(collection_id=collection_id)

        # Query all Vespa schemas - use 'contains' for YQL queries (admin_sync_service.py line 679)
        schemas = "base_entity, file_entity, code_file_entity, email_entity, web_entity"
        yql = (
            f"select * from sources {schemas} "
            f"where airweave_system_metadata_sync_id contains '{sync_id}' "
            f"and airweave_system_metadata_collection_id contains '{collection_id}' "
            f"limit 0"
        )

        query_params = {"yql": yql}
        response = await vespa._client.execute_query(query_params)
        return response.total_count if response.total_count is not None else 0
    except Exception as e:
        print(f"    Warning: Vespa query failed for sync {sync_id}: {e}", flush=True)
        return 0


async def check_sync(
    conn, sync_id: UUID, collection_id: str
) -> Tuple[UUID, int, int, int, List[str]]:
    """Check a single sync and return counts and issues.

    Returns:
        Tuple of (sync_id, pg_count, arf_count, vespa_count, issues)
    """
    pg_count = await get_postgres_entity_count(conn, sync_id)
    arf_count = await get_arf_entity_count(sync_id)
    vespa_count = await get_vespa_document_count(sync_id, collection_id)

    issues = []

    # Check Vespa issues
    if vespa_count == 0 and pg_count > 0:
        issues.append("Vespa empty")
    elif vespa_count < pg_count:
        issues.append(f"Vespa < PG ({pg_count - vespa_count} missing)")

    # Check ARF issues
    if arf_count == 0 and pg_count > 0:
        issues.append("ARF missing")
    elif pg_count > arf_count:
        issues.append(f"PG > ARF ({pg_count - arf_count} more)")

    return (sync_id, pg_count, arf_count, vespa_count, issues)


async def main():
    """Main execution function."""
    print("=" * 100, flush=True)
    print("Vespa & ARF Gap Checker", flush=True)
    print("=" * 100, flush=True)
    print(flush=True)

    # Connect to PostgreSQL
    conn = await get_postgres_connection()

    try:
        # Get all syncs
        print("Fetching all non-orphaned syncs from database...", flush=True)
        syncs = await get_all_syncs(conn)
        print(f"✓ Found {len(syncs)} non-orphaned syncs\n", flush=True)

        if not syncs:
            print("No syncs found in database.", flush=True)
            return

        print("Checking counts (this may take a while)...", flush=True)
        print(flush=True)

        # Check each sync
        results = []
        for i, sync_data in enumerate(syncs, 1):
            if i % 10 == 0:
                print(f"Progress: {i}/{len(syncs)} syncs checked...", flush=True)

            result = await check_sync(conn, sync_data["sync_id"], sync_data["collection_id"])
            results.append(result)

        print(f"✓ Completed checking {len(syncs)} syncs\n", flush=True)

        # Filter syncs with issues
        syncs_with_issues = [r for r in results if r[4]]  # r[4] is the issues list

        # Print summary
        print("=" * 100, flush=True)
        print("SUMMARY", flush=True)
        print("=" * 100, flush=True)
        print(f"Total syncs checked: {len(results)}", flush=True)
        print(f"Syncs with issues: {len(syncs_with_issues)}", flush=True)
        print(f"Syncs OK: {len(results) - len(syncs_with_issues)}", flush=True)
        print(flush=True)

        if syncs_with_issues:
            print("=" * 100, flush=True)
            print("SYNCS WITH ISSUES", flush=True)
            print("=" * 100, flush=True)
            print(flush=True)
            print(f"{'Sync ID':<38} {'PG':<12} {'ARF':<12} {'Vespa':<12} {'Issues'}", flush=True)
            print("-" * 100, flush=True)

            for sync_id, pg_count, arf_count, vespa_count, issues in syncs_with_issues:
                issues_str = ", ".join(issues)
                print(
                    f"{str(sync_id):<38} {pg_count:<12} {arf_count:<12} "
                    f"{vespa_count:<12} {issues_str}",
                    flush=True,
                )

            print(flush=True)
            print("=" * 100, flush=True)
            print("SYNC IDS WITH VESPA ISSUES (for resync)", flush=True)
            print("=" * 100, flush=True)

            # Only output syncs with Vespa issues
            vespa_issue_syncs = [
                r for r in syncs_with_issues if any("Vespa" in issue for issue in r[4])
            ]

            for sync_id, _, _, _, _ in vespa_issue_syncs:
                print(sync_id, flush=True)

            print(flush=True)
            print("=" * 100, flush=True)
            print("SYNC IDS WITH ARF ISSUES", flush=True)
            print("=" * 100, flush=True)

            # Only output syncs with ARF issues
            arf_issue_syncs = [
                r for r in syncs_with_issues if any("ARF" in issue for issue in r[4])
            ]

            for sync_id, _, _, _, _ in arf_issue_syncs:
                print(sync_id, flush=True)

            print(flush=True)
        else:
            print("✓ All syncs have consistent Vespa and ARF storage!", flush=True)
            print(flush=True)

    finally:
        await conn.close()
        print("✓ Database connection closed", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
