"""Enhanced search service with configurable operations.

This service uses a modular architecture where search functionality
is broken down into composable operations that can be configured
and executed in a flexible pipeline.
"""

import time

from sqlalchemy.ext.asyncio import AsyncSession

from airweave import crud
from airweave.api.context import ApiContext
from airweave.core.exceptions import NotFoundException
from airweave.schemas.search import SearchRequest, SearchResponse
from airweave.search.factory import factory
from airweave.search.helpers import search_helpers
from airweave.search.orchestrator import orchestrator


class SearchService:
    """Search service."""

    async def search(
        self,
        request_id: str,
        readable_collection_id: str,
        search_request: SearchRequest,
        stream: bool,
        db: AsyncSession,
        ctx: ApiContext,
    ) -> SearchResponse:
        """Search a collection."""
        start_time = time.monotonic()

        collection = await crud.collection.get_by_readable_id(
            db, readable_id=readable_collection_id, ctx=ctx
        )
        if not collection:
            raise NotFoundException(detail=f"Collection '{readable_collection_id}' not found")

        ctx.logger.debug("Building search context")
        search_context = factory.build(
            request_id, collection.id, readable_collection_id, search_request, stream, ctx
        )

        ctx.logger.debug("Executing search")
        response = await orchestrator.run(ctx, search_context)

        duration_ms = (time.monotonic() - start_time) * 1000
        ctx.logger.debug(f"Search completed in {duration_ms:.2f}ms")

        await search_helpers.persist_search_data(
            db=db,
            search_context=search_context,
            search_response=response,
            ctx=ctx,
            duration_ms=duration_ms,
        )

        return response


# TODO: clean search results


service = SearchService()
