#!/usr/bin/env python3
"""Quick test script to verify Vespa query works before running full scan."""

import asyncio
from uuid import UUID


async def test_vespa_query():
    from airweave.platform.destinations.vespa import VespaDestination

    # Test with a known sync ID from the production data
    test_sync_id = UUID("eac29a9c-dbdd-4316-bf58-99ad946009cb")
    test_collection_id = "linkup-h7p78l"

    print(f"Testing Vespa query for sync {test_sync_id} in collection {test_collection_id}")

    vespa = await VespaDestination.create(collection_id=test_collection_id)

    schemas = "base_entity, file_entity, code_file_entity, email_entity, web_entity"
    yql = (
        f"select * from sources {schemas} "
        f"where airweave_system_metadata_sync_id contains '{test_sync_id}' "
        f"and airweave_system_metadata_collection_id contains '{test_collection_id}' "
        f"limit 0"
    )

    print(f"YQL: {yql}")

    query_params = {"yql": yql}
    response = await vespa._client.execute_query(query_params)

    print(f"✓ Query succeeded!")
    print(f"  Total count: {response.total_count}")

    return response.total_count


if __name__ == "__main__":
    count = asyncio.run(test_vespa_query())
    print(f"\nFinal count: {count}")
