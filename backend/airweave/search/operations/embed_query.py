"""Query embedding operation.

Converts text queries into vector embeddings for similarity search.
Generates dense neural embeddings and/or sparse BM25 embeddings based on
the retrieval strategy (hybrid, neural, or keyword).
"""

from typing import Any, List

from airweave.api.context import ApiContext
from airweave.platform.embedding_models.bm25_text2vec import BM25Text2Vec
from airweave.schemas.search import RetrievalStrategy
from airweave.search.context import SearchContext
from airweave.search.providers._base import BaseProvider

from ._base import SearchOperation


class EmbedQuery(SearchOperation):
    """Generate vector embeddings for queries."""

    def __init__(self, strategy: RetrievalStrategy, provider: BaseProvider) -> None:
        """Initialize with retrieval strategy and provider."""
        self.strategy = strategy
        self.provider = provider

    def depends_on(self) -> List[str]:
        """Depends on query expansion to get all queries to embed."""
        return ["QueryExpansion"]

    async def execute(self, context: SearchContext, state: dict[str, Any], ctx: ApiContext) -> None:
        """Generate embeddings for queries."""
        ctx.logger.debug("[EmbedQuery] Generating embeddings for queries")

        # Determine queries to embed (expanded + original, or just original)
        queries = self._get_queries_to_embed(context, state)

        # Generate dense embeddings if needed
        # Note: Token validation is handled by the provider in its embed() method
        if self.strategy in (RetrievalStrategy.HYBRID, RetrievalStrategy.NEURAL):
            dense_embeddings = await self._generate_dense_embeddings(queries, ctx)
        else:
            # Keyword-only doesn't need dense embeddings
            dense_embeddings = None

        # Generate sparse BM25 embeddings if needed
        if self.strategy in (RetrievalStrategy.HYBRID, RetrievalStrategy.KEYWORD):
            sparse_embeddings = await self._generate_sparse_embeddings(queries, ctx)
        else:
            sparse_embeddings = None

        # Write to state - embeddings are REQUIRED, never write None
        if dense_embeddings is None and sparse_embeddings is None:
            raise RuntimeError(
                f"No embeddings generated for strategy {self.strategy}. This is a bug."
            )

        state["dense_embeddings"] = dense_embeddings
        state["sparse_embeddings"] = sparse_embeddings

    def _get_queries_to_embed(self, context: SearchContext, state: dict[str, Any]) -> List[str]:
        """Get all queries to embed (original + expanded)."""
        queries = [context.query]

        # Add expanded queries if available
        expanded = state.get("expanded_queries", [])
        if expanded:
            queries.extend(expanded)

        if not queries:
            raise ValueError("No queries to embed")

        return queries

    async def _generate_dense_embeddings(
        self, queries: List[str], ctx: ApiContext
    ) -> List[List[float]]:
        """Generate dense neural embeddings using provider."""
        dense_embeddings = await self.provider.embed(queries)

        # Validate we got embeddings for all queries
        if len(dense_embeddings) != len(queries):
            raise RuntimeError(
                f"Embedding count mismatch: got {len(dense_embeddings)} for {len(queries)} queries"
            )

        ctx.logger.debug(f"[EmbedQuery] Dense embeddings generated: {len(dense_embeddings)}")

        return dense_embeddings

    async def _generate_sparse_embeddings(self, queries: List[str], ctx: ApiContext) -> List:
        """Generate sparse BM25 embeddings for keyword search."""
        # BM25 is local and always available
        bm25_embedder = BM25Text2Vec(logger=None)

        # Generate sparse embeddings
        if len(queries) == 1:
            sparse_embedding = await bm25_embedder.embed(queries[0])
            sparse_embeddings = [sparse_embedding]
        else:
            sparse_embeddings = await bm25_embedder.embed_many(queries)

        # Validate we got embeddings for all queries
        if len(sparse_embeddings) != len(queries):
            raise RuntimeError(
                f"Sparse embedding count mismatch: got {len(sparse_embeddings)} "
                f"for {len(queries)} queries"
            )

        ctx.logger.debug(f"[EmbedQuery] Sparse embeddings generated: {len(sparse_embeddings)}")

        return sparse_embeddings
