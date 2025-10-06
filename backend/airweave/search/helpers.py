"""Helpers for search."""

from pathlib import Path
from uuid import UUID

import yaml
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from airweave import crud
from airweave.api.context import ApiContext
from airweave.schemas.search import SearchRequest, SearchResponse
from airweave.schemas.search_query import SearchQueryCreate


class SearchHelpers:
    """Helpers for search."""

    async def persist_search_data(
        self,
        db: AsyncSession,
        search_request: SearchRequest,
        search_response: SearchResponse,
        collection_id: str,
        ctx: ApiContext,
        duration_ms: float,
        collection_slug: str,
    ) -> None:
        """Persist search data for analytics and user experience."""
        try:
            # Convert collection_id to UUID if it's a string

            collection_uuid = (
                UUID(collection_id) if isinstance(collection_id, str) else collection_id
            )

            # Determine search status
            status = self._determine_search_status(search_response)

            # Extract API key ID from auth metadata if available
            api_key_id = None
            if ctx.is_api_key_auth and ctx.auth_metadata:
                api_key_id = ctx.auth_metadata.get("api_key_id")

            # Create search query schema following the standard pattern
            search_query_create = SearchQueryCreate(
                collection_id=collection_uuid,
                organization_id=ctx.organization.id,
                user_id=ctx.user.id if ctx.user else None,
                api_key_id=UUID(api_key_id) if api_key_id else None,
                query_text=search_request.query,
                query_length=len(search_request.query),
                search_type=self._determine_search_type(search_request),
                response_type=(
                    search_request.response_type.value if search_request.response_type else None
                ),
                limit=search_request.limit,
                offset=search_request.offset,
                score_threshold=search_request.score_threshold,
                recency_bias=search_request.recency_bias,
                search_method=search_request.search_method,
                filters=search_request.filter.model_dump() if search_request.filter else None,
                duration_ms=int(duration_ms),
                results_count=len(search_response.results),
                status=status,
                query_expansion_enabled=(
                    search_request.expansion_strategy != "no_expansion"
                    if search_request.expansion_strategy
                    else None
                ),
                reranking_enabled=(
                    search_request.enable_reranking
                    if search_request.enable_reranking is not None
                    else None
                ),
                query_interpretation_enabled=(
                    search_request.enable_query_interpretation
                    if search_request.enable_query_interpretation is not None
                    else None
                ),
            )

            # Create search query record using standard CRUD pattern
            await crud.search_query.create(db=db, obj_in=search_query_create, ctx=ctx)

            ctx.logger.debug(
                f"[SearchServiceV2] Search data persisted successfully for query: "
                f"'{search_request.query[:50]}...'"
            )

        except Exception as e:
            # Don't fail the search if persistence fails
            ctx.logger.error(
                f"[SearchServiceV2] Failed to persist search data: {str(e)}. "
                f"Search completed successfully but analytics data was not saved."
            )

    def _determine_search_status(self, search_response: SearchResponse) -> str:
        """Determine search status from response."""
        if hasattr(search_response, "status") and search_response.status:
            return search_response.status
        return "success" if search_response.results else "no_results"

    def _determine_search_type(self, search_request: SearchRequest) -> str:
        """Determine search type from request parameters."""
        if search_request.filter:
            return "advanced"
        return "basic"

    @staticmethod
    def load_defaults() -> dict:
        """Load search defaults from yaml."""
        path = Path(__file__).with_name("defaults.yml")
        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                raise ValueError("YAML root must be a mapping")
            search_defaults = data.get("search_defaults")
            if not isinstance(search_defaults, dict) or not search_defaults:
                raise ValueError("'search_defaults' missing or empty")
            return data  # Return full data dict with all keys
        except Exception as e:
            raise HTTPException(status_code=500, detail="Failed to load search defaults") from e


search_helpers = SearchHelpers()
