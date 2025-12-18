"""Vespa retrieval operation.

Performs hybrid search against Vespa using the configured query profile.
Vespa handles embedding generation server-side, so this operation takes
text queries directly (no client-side embeddings needed).
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List
from uuid import UUID

from airweave.api.context import ApiContext
from airweave.core.config import settings
from airweave.search.context import SearchContext

from ._base import SearchOperation


class VespaRetrieval(SearchOperation):
    """Execute hybrid search against Vespa.

    Unlike QdrantRetrieval, this operation:
    - Takes text queries directly (no embeddings)
    - Uses Vespa's server-side embedding via nomic-ai-modernbert
    - Uses the 'hybrid' query profile for combined BM25 + vector search
    - Filters by collection_id for multi-tenant isolation
    """

    def __init__(self, collection_id: UUID, limit: int, offset: int) -> None:
        """Initialize with retrieval configuration.

        Args:
            collection_id: Collection UUID for multi-tenant filtering
            limit: Maximum number of results to return
            offset: Number of results to skip (pagination)
        """
        self.collection_id = collection_id
        self.limit = limit
        self.offset = offset

    def depends_on(self) -> List[str]:
        """Depends on QueryExpansion (but not EmbedQuery - Vespa embeds server-side)."""
        return ["QueryExpansion"]

    async def execute(
        self,
        context: SearchContext,
        state: dict[str, Any],
        ctx: ApiContext,
    ) -> None:
        """Execute hybrid search against Vespa."""
        ctx.logger.debug("[VespaRetrieval] Executing search against Vespa")

        # Emit search start event
        await context.emitter.emit(
            "vector_search_start",
            {
                "method": "hybrid",
                "backend": "vespa",
                "collection_id": str(self.collection_id),
            },
            op_name=self.__class__.__name__,
        )

        # Import pyvespa
        from vespa.application import Vespa

        # Create Vespa client
        app = Vespa(url=settings.VESPA_URL, port=settings.VESPA_PORT)

        # Build query parameters for hybrid search
        query_params = {
            "query": context.query,
            "queryProfile": "hybrid",
            "collection_id": str(self.collection_id),
            "hits": self.limit + self.offset,  # Fetch extra for offset
            "presentation.summary": "default",  # Get full document fields
        }

        ctx.logger.debug(f"[VespaRetrieval] Query params: {query_params}")

        # Execute query in thread pool (pyvespa is synchronous)
        try:
            response = await asyncio.to_thread(app.query, query_params)
        except Exception as e:
            ctx.logger.error(f"[VespaRetrieval] Vespa query failed: {e}")
            raise RuntimeError(f"Vespa search failed: {e}") from e

        # Check for errors
        if not response.is_successful():
            error_msg = getattr(response, "json", {}).get("error", str(response))
            ctx.logger.error(f"[VespaRetrieval] Vespa returned error: {error_msg}")
            raise RuntimeError(f"Vespa search error: {error_msg}")

        # Convert Vespa results to Qdrant-compatible format
        raw_results = self._convert_vespa_results(response, ctx)

        # Apply offset (pagination)
        if self.offset > 0:
            raw_results = raw_results[self.offset :]

        # Limit results
        final_results = raw_results[: self.limit]

        ctx.logger.debug(f"[VespaRetrieval] Retrieved {len(final_results)} results")

        # Write to state
        state["results"] = final_results

        # Report metrics for analytics
        self._report_metrics(
            state,
            output_count=len(raw_results),
            final_count=len(final_results),
            search_method="hybrid",
            backend="vespa",
        )

        # Emit search done event
        top_scores = [r.get("score", 0) for r in final_results[:3]]
        await context.emitter.emit(
            "vector_search_done",
            {
                "final_count": len(final_results),
                "top_scores": top_scores,
                "backend": "vespa",
            },
            op_name=self.__class__.__name__,
        )

        # Emit special event if no results
        if not final_results:
            await context.emitter.emit(
                "vector_search_no_results",
                {
                    "reason": "no_matching_documents",
                    "backend": "vespa",
                },
                op_name=self.__class__.__name__,
            )

    def _convert_vespa_results(self, response: Any, ctx: ApiContext) -> List[Dict[str, Any]]:
        """Convert Vespa response to Qdrant-compatible format.

        Vespa returns:
        - hit['id']: Document ID (e.g., "id:airweave:base_entity::AsanaTaskEntity_123")
        - hit['relevance']: Relevance score
        - hit['fields']: Document fields

        We convert to Qdrant format:
        - result['id']: Document ID
        - result['score']: Relevance score
        - result['payload']: Document fields (renamed from 'fields')

        Args:
            response: VespaQueryResponse from pyvespa
            ctx: API context for logging

        Returns:
            List of results in Qdrant-compatible format
        """
        results = []

        # Get hits from response
        hits = response.hits or []

        for hit in hits:
            try:
                # Extract fields from hit
                fields = hit.get("fields", {})

                # Build Qdrant-compatible result
                result = {
                    "id": hit.get("id", ""),
                    "score": hit.get("relevance", 0.0),
                    "payload": {
                        # Core entity fields
                        "entity_id": fields.get("entity_id", ""),
                        "name": fields.get("name", ""),
                        "source_name": fields.get("source_name", ""),
                        "entity_type": fields.get("entity_type", ""),
                        "textual_representation": fields.get("textual_representation", ""),
                        # Breadcrumbs (convert from Vespa struct format if needed)
                        "breadcrumbs": self._extract_breadcrumbs(fields),
                        # Timestamps
                        "created_at": fields.get("created_at"),
                        "updated_at": fields.get("updated_at"),
                        # System metadata
                        "collection_id": fields.get("collection_id", ""),
                        "sync_id": fields.get("sync_id", ""),
                        # Payload (extra fields stored as JSON)
                        "payload": fields.get("payload", {}),
                    },
                }

                results.append(result)

            except Exception as e:
                ctx.logger.warning(f"[VespaRetrieval] Failed to convert hit: {e}")
                continue

        return results

    def _extract_breadcrumbs(self, fields: Dict[str, Any]) -> List[Dict[str, str]]:
        """Extract breadcrumbs from Vespa fields.

        Vespa stores breadcrumbs as an array of structs with 'label' and 'url' fields.

        Args:
            fields: Vespa document fields

        Returns:
            List of breadcrumb dicts with 'label' and 'url' keys
        """
        breadcrumbs = fields.get("breadcrumbs", [])

        if not breadcrumbs:
            return []

        # Breadcrumbs should already be in the right format from Vespa
        if isinstance(breadcrumbs, list):
            return [
                {"label": b.get("label", ""), "url": b.get("url", "")}
                for b in breadcrumbs
                if isinstance(b, dict)
            ]

        return []
