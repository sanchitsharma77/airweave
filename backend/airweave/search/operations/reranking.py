"""Reranking operation.

Provider-agnostic reranking that reorders retrieval results using the
`rerank` capability of the configured provider. The provider is responsible
for handling its own constraints (token windows, max docs, truncation).
This operation:
  - Reads `results` from state (produced by `Retrieval`)
  - Prepares provider documents from result payloads
  - Calls provider.rerank(query, documents, top_n)
  - Applies the returned ranking to reorder results
  - Writes reordered list back to `state["results"]`
"""

from typing import Any, List

from airweave.search.context import SearchContext
from airweave.search.providers._base import BaseProvider

from ._base import SearchOperation


class Reranking(SearchOperation):
    """Rerank search results using LLM for improved relevance."""

    def __init__(self, provider: BaseProvider) -> None:
        """Initialize with LLM provider.

        Args:
            provider: LLM provider for reranking (guaranteed by factory)
        """
        self.provider = provider

    def depends_on(self) -> List[str]:
        """Depends on retrieval to have results to rerank."""
        return ["Retrieval"]

    async def execute(self, context: SearchContext, state: dict[str, Any]) -> None:
        """Rerank results using the configured provider."""
        results = state.get("results")

        if results is None:
            raise RuntimeError("Reranking requires 'results' in state from Retrieval operation")
        if not isinstance(results, list):
            raise ValueError(f"Expected 'results' to be a list, got {type(results)}")
        if len(results) == 0:
            state["results"] = []
            return

        documents, top_n = self._prepare_inputs(context, results)

        if not documents:
            raise RuntimeError(
                f"Document preparation produced no documents from {len(results)} results. "
                "This indicates a bug in document extraction logic."
            )

        rankings = await self.provider.rerank(context.query, documents, top_n)

        if not isinstance(rankings, list) or not rankings:
            raise RuntimeError("Provider returned empty or invalid rankings")

        state["results"] = self._apply_rankings(results, rankings, top_n)

    def _prepare_inputs(self, context: SearchContext, results: List[dict]) -> tuple[List[str], int]:
        """Prepare documents for reranking."""
        if not results:
            return [], 0

        # Get provider's max_documents limit if configured (Cohere has this)
        max_docs = None
        if self.provider.model_spec.rerank_model:
            max_docs = self.provider.model_spec.rerank_model.max_documents

        # Cap results to provider's limit if specified
        if max_docs and len(results) > max_docs:
            results_to_rerank = results[:max_docs]
        else:
            results_to_rerank = results

        documents = self._prepare_documents(results_to_rerank)
        limit = getattr(context.retrieval, "limit", len(results))
        top_n = min(len(documents), limit)
        if top_n < 1:
            raise ValueError("Computed top_n < 1 for reranking")
        return documents, top_n

    def _prepare_documents(self, results: List[dict]) -> List[str]:
        """Create provider document strings from result payloads."""
        documents: List[str] = []
        for i, result in enumerate(results):
            if not isinstance(result, dict):
                raise ValueError(f"Result at index {i} is not a dict: {type(result)}")
            payload = result.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}

            source = payload.get("source_name") or payload.get("source") or ""
            title = payload.get("md_title") or payload.get("title") or payload.get("name") or ""
            content = (
                payload.get("embeddable_text")
                or payload.get("md_content")
                or payload.get("content")
                or payload.get("text")
                or ""
            )

            # Compose a single string; providers may add additional formatting
            parts = []
            if source:
                parts.append(f"Source: {source}")
            if title:
                parts.append(f"Title: {title}")
            if content:
                parts.append(f"Content: {content}")
            doc = "\n".join(parts) if parts else ""
            if not doc:
                # Keep empty string to preserve index alignment; provider will handle/raise
                doc = ""
            documents.append(doc)

        return documents

    def _apply_rankings(self, results: List[dict], rankings: List[dict], top_n: int) -> List[dict]:
        ranked_indices = self._validate_and_extract_indices(rankings, len(results))

        seen = set()
        ordered: List[dict] = []
        for idx in ranked_indices:
            if idx not in seen:
                ordered.append(results[idx])
                seen.add(idx)

        for i, r in enumerate(results):
            if len(ordered) >= top_n:
                break
            if i not in seen:
                ordered.append(r)

        return ordered[:top_n]

    def _validate_and_extract_indices(self, rankings: List[dict], results_len: int) -> List[int]:
        """Extract and validate ranking indices."""
        indices: List[int] = []
        for item in rankings:
            if not isinstance(item, dict):
                raise ValueError("Ranking item must be a dict with 'index' and 'relevance_score'")
            if "index" not in item:
                raise ValueError("Ranking item missing 'index'")
            idx = int(item["index"])
            if idx < 0 or idx >= results_len:
                raise IndexError("Ranking index out of bounds")
            indices.append(idx)
        return indices
