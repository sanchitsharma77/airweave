"""Cohere-based reranking operation.

This module contains the LLM reranking operation that uses Cohere's
Rerank API to reorder search results based on relevance to the query.
"""

from typing import Any, Dict, List, Optional

try:  # pragma: no cover - import resolution can vary in dev environments
    import cohere  # type: ignore
except Exception:  # noqa: BLE001
    cohere = None  # type: ignore[assignment]

import yaml

from airweave.core.config import settings
from airweave.search.operations.base import SearchOperation


class LLMReranking(SearchOperation):
    """Rerank search results using Cohere Rerank API."""

    def __init__(
        self,
        model: str = "rerank-v3.5",
        max_candidates: int = 100,
        max_docs: int = 1000,
        max_tokens_per_doc: int = 4096,
    ):
        """Initialize Cohere reranking.

        Args:
            model: Cohere Rerank model identifier (e.g., "rerank-v3.5")
            max_candidates: Maximum number of top results to send to Cohere
            max_docs: Hard cap of documents sent to Cohere (API best practice: ≤ 1000)
            max_tokens_per_doc: Max tokens per document (Cohere default is 4096)
        """
        self.model = model
        self.max_candidates = max(1, int(max_candidates))
        self.max_docs = max(1, int(max_docs))
        self.max_tokens_per_doc = max(256, int(max_tokens_per_doc))

    @property
    def name(self) -> str:
        """Operation name."""
        return "llm_reranking"

    @property
    def depends_on(self) -> List[str]:
        """Reranking depends on vector search."""
        return ["vector_search"]

    async def execute(self, context: Dict[str, Any]) -> None:  # noqa: C901
        """Execute Cohere-based reranking.

        Reads from context:
            - raw_results: Initial search results
            - query: Original search query
            - config: SearchConfig
            - logger: For logging

        Writes to context:
            - final_results: Reranked and limited results
        """
        results = context.get("raw_results", [])
        query = context["query"]
        config = context["config"]
        logger = context["logger"]
        cohere_api_key = getattr(settings, "COHERE_API_KEY", None)

        if not results:
            context["final_results"] = []
            logger.debug(f"[{self.name}] No results to rerank")
            return

        if not cohere_api_key:
            # Graceful degradation per search rules: return unmodified results
            logger.warning(f"[{self.name}] COHERE_API_KEY not configured; skipping reranking")
            context["final_results"] = results[: config.limit]
            raise RuntimeError("COHERE_API_KEY not configured; skipping reranking")

        logger.debug(f"[{self.name}] Reranking {len(results)} results using Cohere {self.model}")

        try:
            # Prepare candidate set
            prepared = self._prepare_candidates(results)
            # Enforce absolute doc cap of 1000 and configured bounds
            effective_k = min(len(prepared), self.max_candidates, self.max_docs, 1000)
            prepared = prepared[:effective_k]

            # Build YAML strings for best model performance on semi-structured data
            yaml_docs: List[str] = []
            # Estimate query tokens for budgeting doc tokens
            query_tokens = self._estimate_tokens(query)
            # Cohere allows query to consume up to half of the context window
            query_cap = min(query_tokens, self.max_tokens_per_doc // 2)
            # Leave headroom for YAML keys/formatting (~64 tokens)
            overhead = 64
            doc_token_budget = max(1, self.max_tokens_per_doc - query_cap - overhead)
            for item in prepared:
                content_truncated = self._truncate_text_to_tokens(
                    item.get("content") or "", doc_token_budget
                )
                doc = {
                    "Title": item.get("title") or "Untitled",
                    "Source": item.get("source") or "Unknown",
                    "Content": content_truncated,
                }
                yaml_docs.append(yaml.dump(doc, sort_keys=False))

            request_id: Optional[str] = context.get("request_id")
            emitter = context.get("emit") if request_id else None
            if callable(emitter):
                await emitter(
                    "reranking_start",
                    {"model": self.model, "strategy": "cohere", "k": len(yaml_docs)},
                    op_name=self.name,
                )

            # Call Cohere Async Rerank API
            logger.debug(f"\n\n{yaml_docs}\n\n")
            client = cohere.AsyncClientV2(api_key=cohere_api_key)
            response = await client.rerank(
                model=self.model,
                query=query,
                documents=yaml_docs,
                top_n=min(config.limit, len(yaml_docs)),
                max_tokens_per_doc=self.max_tokens_per_doc,
            )

            # Map reranked indices (relative to yaml_docs) back to original results indices
            rankings_list: List[Dict[str, Any]] = []
            ranked_original_indices: List[int] = []
            for r in response.results:  # type: ignore[attr-defined]
                doc_idx = int(getattr(r, "index", 0))
                score = float(getattr(r, "relevance_score", 0.0))
                if 0 <= doc_idx < len(prepared):
                    original_idx = int(prepared[doc_idx]["index"])  # index in `results`
                    rankings_list.append({"index": original_idx, "relevance_score": score})
                    ranked_original_indices.append(original_idx)

            # Apply final ranking and enforce limit
            context["final_results"] = self._apply_ranking_from_indices(
                results=results, ranked_indices=ranked_original_indices, limit=config.limit
            )

            logger.debug(
                f"[{self.name}] Successfully reranked; returned "
                f"{len(context['final_results'])} results"
            )

            # Emit finish events
            await self._emit_finish_events(emitter, rankings_list)

        except Exception as e:
            logger.error(f"[{self.name}] Cohere reranking failed: {e}", exc_info=True)
            # Graceful degradation
            context["final_results"] = results[: config.limit]

    # ----------------------------- Helpers ------------------------------------
    def _prepare_candidates(self, results: List[Dict]) -> List[Dict[str, Any]]:
        k = min(len(results), self.max_candidates)
        prepared: List[Dict[str, Any]] = []
        for i, result in enumerate(results[:k]):
            payload = result.get("payload", {})
            # Prefer embeddable_text as the primary text for LLM consumption,
            # falling back to chunk/content/text as needed.
            content = (
                payload.get("embeddable_text")
                or payload.get("md_content")
                or payload.get("content")
                or payload.get("text", "")
            )
            prepared.append(
                {
                    "index": i,
                    "source": payload.get("source_name", "Unknown"),
                    # Prefer richer, domain-aware titles first
                    "title": payload.get("md_title")
                    or payload.get("title")
                    or payload.get("name")
                    or "Untitled",
                    "content": content,
                    "embeddable_text": payload.get("embeddable_text", ""),
                    "score": result.get("score", 0),
                }
            )
        return prepared

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimator (~4 chars/token)."""
        try:
            return int(len(text) / 4)
        except Exception:
            return int(float(len(text)) / 4)

    def _truncate_text_to_tokens(self, text: str, max_tokens: int) -> str:
        if max_tokens <= 0 or not text:
            return ""
        # Fast path by characters using estimator, then refine if needed
        approx_chars = max_tokens * 4
        if len(text) <= approx_chars:
            return text
        truncated = text[:approx_chars]
        # Ensure we do not exceed the token budget significantly
        while self._estimate_tokens(truncated) > max_tokens and len(truncated) > 0:
            truncated = truncated[:-256]
        return truncated

    def _apply_ranking_from_indices(
        self, *, results: List[Dict[str, Any]], ranked_indices: List[int], limit: int
    ) -> List[Dict[str, Any]]:
        final_results: List[Dict[str, Any]] = []
        seen = set()
        for idx in ranked_indices:
            if 0 <= idx < len(results) and idx not in seen:
                final_results.append(results[idx])
                seen.add(idx)

        for i, result in enumerate(results):
            if i not in seen and len(final_results) < limit:
                final_results.append(result)
        return final_results[:limit]

    async def _emit_finish_events(
        self, emitter: Optional[Any], rankings_list: List[Dict[str, Any]]
    ) -> None:
        if not callable(emitter):
            return
        try:
            if rankings_list:
                await emitter("rankings", {"rankings": rankings_list}, op_name=self.name)
        except Exception:
            pass
        try:
            await emitter(
                "reranking_done",
                {"rankings": rankings_list, "applied": bool(rankings_list)},
                op_name=self.name,
            )
        except Exception:
            pass
