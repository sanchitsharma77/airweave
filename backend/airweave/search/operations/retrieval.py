"""Retrieval operation.

Performs the actual vector similarity search against Qdrant using embeddings,
filters, and optional temporal decay. This is the core search operation that
queries the vector database.
"""

from typing import Any, Dict, List

from airweave.api.context import ApiContext
from airweave.platform.destinations.qdrant import QdrantDestination
from airweave.schemas.search import RetrievalStrategy
from airweave.search.context import SearchContext

from ._base import SearchOperation


class Retrieval(SearchOperation):
    """Execute vector similarity search in Qdrant."""

    RERANK_PREFETCH_MULTIPLIER = 2.0  # Fetch 2x more candidates for reranking

    def __init__(self, strategy: RetrievalStrategy, offset: int, limit: int) -> None:
        """Initialize with retrieval configuration."""
        self.strategy = strategy
        self.offset = offset
        self.limit = limit

    def depends_on(self) -> List[str]:
        """Depends on operations that provide embeddings, filter, and decay config."""
        return ["QueryInterpretation", "EmbedQuery", "UserFilter", "TemporalRelevance"]

    async def execute(self, context: SearchContext, state: dict[str, Any], ctx: ApiContext) -> None:
        """Execute vector search against Qdrant."""
        ctx.logger.debug("[Retrieval] Executing search against Qdrant")

        # Get inputs from state (embeddings validated by EmbedQuery)
        dense_embeddings = state.get("dense_embeddings")
        sparse_embeddings = state.get("sparse_embeddings")
        filter_dict = state.get("filter")
        decay_config = state.get("decay_config")

        # Determine search method from strategy
        search_method = self._get_search_method()

        # Connect to Qdrant
        destination = await QdrantDestination.create(
            collection_id=context.collection_id, logger=None
        )

        # Execute search (single vs bulk have different pagination strategies)
        is_bulk = len(dense_embeddings or sparse_embeddings) > 1

        if is_bulk:
            ctx.logger.debug("[Retrieval] Executing bulk search")
            # Multiple queries - deduplicate then paginate
            results = await self._execute_bulk_search(
                destination,
                dense_embeddings,
                sparse_embeddings,
                filter_dict,
                decay_config,
                search_method,
                context,
                ctx,
            )
            # Apply offset and limit after deduplication
            final_results = self._apply_pagination(results)
        else:
            ctx.logger.debug("[Retrieval] Executing single search")
            # Single query - Qdrant handles offset, we just fetch limit
            final_results = await self._execute_single_search(
                destination,
                dense_embeddings,
                sparse_embeddings,
                filter_dict,
                decay_config,
                search_method,
                context,
                ctx,
            )

        # Write to state
        ctx.logger.debug(f"[Retrieval] results: {len(final_results)}")
        state["results"] = final_results

    def _get_search_method(self) -> str:
        """Map RetrievalStrategy to Qdrant search method."""
        mapping = {
            RetrievalStrategy.HYBRID: "hybrid",
            RetrievalStrategy.NEURAL: "neural",
            RetrievalStrategy.KEYWORD: "keyword",
        }
        return mapping[self.strategy]

    def _calculate_fetch_limit(self, has_reranking: bool, include_offset: bool) -> int:
        """Calculate how many results to fetch from Qdrant."""
        base_limit = self.limit
        if include_offset:
            base_limit += self.offset

        if has_reranking:
            # Fetch extra candidates for better reranking
            return int(base_limit * self.RERANK_PREFETCH_MULTIPLIER)

        return base_limit

    async def _execute_single_search(
        self,
        destination: QdrantDestination,
        dense_embeddings: List[List[float]],
        sparse_embeddings: List,
        filter_dict: dict,
        decay_config: Any,
        search_method: str,
        context: SearchContext,
        ctx: ApiContext,
    ) -> List[Dict]:
        """Execute single query search - Qdrant handles offset."""
        query_vector = dense_embeddings[0] if dense_embeddings else None
        sparse_vector = sparse_embeddings[0] if sparse_embeddings else None

        # Calculate limit (Qdrant handles offset, so don't include it)
        fetch_limit = self._calculate_fetch_limit(
            has_reranking=context.reranking is not None,
            include_offset=False,
        )

        ctx.logger.debug(f"[Retrieval] Fetch limit: {fetch_limit}")

        results = await destination.search(
            query_vector=query_vector,
            limit=fetch_limit,
            offset=self.offset,  # Qdrant handles offset efficiently
            with_payload=True,
            filter=filter_dict,
            sparse_vector=sparse_vector,
            search_method=search_method,
            decay_config=decay_config,
        )

        if not isinstance(results, list):
            raise RuntimeError(f"Expected list of results, got {type(results)}")

        # If reranking, apply limit (Qdrant gave us extra candidates)
        if context.reranking is not None and len(results) > self.limit:
            results = results[: self.limit]

        return results

    async def _execute_bulk_search(
        self,
        destination: QdrantDestination,
        dense_embeddings: List[List[float]],
        sparse_embeddings: List,
        filter_dict: dict,
        decay_config: Any,
        search_method: str,
        context: SearchContext,
        ctx: ApiContext,
    ) -> List[Dict]:
        """Execute bulk search - offset applied after deduplication."""
        # Calculate limit (include offset since we apply it manually)
        fetch_limit = self._calculate_fetch_limit(
            has_reranking=context.reranking is not None,
            include_offset=True,
        )
        ctx.logger.debug(f"[Retrieval] Fetch limit: {fetch_limit}")

        num_queries = len(dense_embeddings or sparse_embeddings)
        filter_conditions = [filter_dict] * num_queries if filter_dict else None

        results = await destination.bulk_search(
            query_vectors=dense_embeddings or [],
            limit=fetch_limit,
            with_payload=True,
            filter_conditions=filter_conditions,
            sparse_vectors=sparse_embeddings,
            search_method=search_method,
            decay_config=decay_config,
        )

        if not isinstance(results, list):
            raise RuntimeError(f"Expected list of results, got {type(results)}")

        # Deduplicate results
        deduplicated = self._deduplicate_results(results)

        return deduplicated

    def _deduplicate_results(self, results: List[Dict]) -> List[Dict]:
        """Deduplicate results keeping highest scores."""
        if not results:
            return []

        best_results = {}

        for result in results:
            if not isinstance(result, dict):
                raise ValueError(f"Invalid result type in search results: {type(result)}")

            # Extract document ID
            doc_id = result.get("id") or result.get("_id")

            if not doc_id and "payload" in result:
                payload = result.get("payload", {})
                if isinstance(payload, dict):
                    doc_id = (
                        payload.get("entity_id")
                        or payload.get("id")
                        or payload.get("_id")
                        or payload.get("db_entity_id")
                    )

            if not doc_id:
                raise ValueError(
                    "Search result missing document ID. Cannot deduplicate. "
                    f"Result: {result.keys() if isinstance(result, dict) else result}"
                )

            score = result.get("score", 0)

            # Keep result with highest score
            if doc_id not in best_results or score > best_results[doc_id].get("score", 0):
                best_results[doc_id] = result

        # Convert to list and sort by score
        merged = list(best_results.values())
        merged.sort(key=lambda x: x.get("score", 0), reverse=True)

        return merged

    def _apply_pagination(self, results: List[Dict]) -> List[Dict]:
        """Apply offset and limit (for bulk search after deduplication)."""
        # Apply offset
        if self.offset > 0:
            results = results[self.offset :] if self.offset < len(results) else []

        # Apply limit
        if len(results) > self.limit:
            results = results[: self.limit]

        return results
