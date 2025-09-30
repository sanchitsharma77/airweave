"""LLM-based reranking operation.

This module contains the LLM reranking operation that uses OpenAI
to reorder search results based on relevance to the original query.
"""

import json as _json
from typing import Any, Dict, List, Optional

from groq import AsyncGroq

from airweave.core.config import settings
from airweave.search.operations.base import SearchOperation


class LLMReranking(SearchOperation):
    """Rerank search results using LLM.

    This operation sends the search results and the original query to
    OpenAI and asks the LLM to rerank the results to ensure the most
    relevant results appear at the top.
    """

    def __init__(self, model: str = "openai/gpt-oss-120b", max_candidates: int = 100):
        """Initialize LLM reranking.

        Args:
            model: OpenAI model to use for reranking
            max_candidates: Maximum number of top results to consider for LLM reranking
        """
        self.model = model
        self.max_candidates = max(1, int(max_candidates))

    @property
    def name(self) -> str:
        """Operation name."""
        return "llm_reranking"

    @property
    def depends_on(self) -> List[str]:
        """Reranking depends on vector search."""
        return ["vector_search"]

    async def execute(self, context: Dict[str, Any]) -> None:  # noqa: C901
        """Execute LLM-based reranking.

        Reads from context:
            - raw_results: Initial search results
            - query: Original search query
            - config: SearchConfig
            - logger: For logging
            - openai_api_key: API key for OpenAI

        Writes to context:
            - final_results: Reranked and limited results
        """
        from pydantic import BaseModel, Field

        results = context.get("raw_results", [])
        query = context["query"]
        config = context["config"]
        logger = context["logger"]
        groq_api_key = getattr(settings, "GROQ_API_KEY", None)

        if not results:
            context["final_results"] = []
            logger.debug(f"[{self.name}] No results to rerank")
            return

        if not groq_api_key:
            # Fail-fast policy: reranking enabled but no key configured
            raise RuntimeError("LLMReranking requires GROQ_API_KEY but none is configured")

        logger.debug(f"[{self.name}] Reranking {len(results)} results using LLM")

        try:
            # Prepare candidate set for the LLM
            logger.debug(f"\n\nResults: {results}\n\n")
            results_for_llm = self._prepare_candidates(results)
            logger.debug(f"\n\nResults for LLM: {results_for_llm}\n\n")

            # Define structured output for reranking (no streaming deltas)
            class RankedResult(BaseModel):
                index: int = Field(description="Original index of the result")
                relevance_score: float = Field(
                    ge=0.0, le=1.0, description="Relevance score from 0 to 1"
                )

            class RerankedResults(BaseModel):
                rankings: List[RankedResult] = Field(
                    description="Results ordered by relevance, most relevant first"
                )

            # Create Groq async client (reads GROQ_API_KEY from environment)
            client = AsyncGroq()

            # Build prompts and budget candidates for context window
            system_prompt = self._build_system_prompt()
            chosen, user_prompt = self._build_user_prompt_with_budget(
                query=query, candidates=results_for_llm
            )

            request_id: Optional[str] = context.get("request_id")
            emitter = context.get("emit") if request_id else None

            # Log number of results included in the prompt
            try:
                logger.debug(
                    f"\n\n[{self.name}] Prompt includes {len(chosen)} candidate(s) "
                    f"out of {len(results_for_llm)} retrieved\n\n"
                )
            except Exception:
                pass

            # Log prompt stats
            self._log_prompt_stats(logger, system_prompt, user_prompt, len(chosen))

            if callable(emitter):
                await emitter(
                    "reranking_start",
                    {"model": self.model, "strategy": "llm", "k": len(chosen)},
                    op_name=self.name,
                )

            # Call Groq Chat Completions with Structured Outputs (non-streaming)
            rankings_list, reranked = await self._call_groq_structured(
                client, system_prompt, user_prompt, RerankedResults, logger
            )

            # Apply final ranking and enforce response limit
            context["final_results"] = self._apply_ranking(
                results=results,
                reranked=reranked,
                limit=config.limit,
            )
            logger.debug(f"[{self.name}] Successfully reranked to {context['final_results']}")

            # Emit finish events
            await self._emit_finish_events(emitter, rankings_list)

        except Exception as e:
            logger.error(f"[{self.name}] Failed: {e}", exc_info=True)
            # Fail-fast per policy
            raise

    def _format_results_for_prompt(self, results: List[Dict]) -> str:
        """Format results for the LLM prompt.

        Args:
            results: List of result dictionaries with index, source, title, content

        Returns:
            Formatted string for the prompt
        """
        formatted = []
        for r in results:
            formatted.append(
                f"[{r['index']}] Source: {r['source']}, Title: {r['title']}\n"
                f"Content: {r['content']}\n"
                f"Original Score: {r['score']:.3f}"
            )
        return "\n\n".join(formatted)

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

    def _build_system_prompt(self) -> str:
        return (
            "You are a search result reranking expert. Your task is to reorder search "
            "results based on their relevance to the user's query.\n\n"
            "Use the vector similarity score as one helpful signal, but do not rely on it "
            "exclusively.\n"
            "- Prioritize direct topical relevance to the user's query\n"
            "- Prefer higher quality, complete, and specific information over vague or "
            "boilerplate text\n"
            "- Consider source reliability and authoritativeness\n"
            "- When items are equally relevant, the higher vector score should break ties\n\n"
            "Only rerank when it improves relevance. If the initial order already reflects "
            "the best results, keep the order unchanged.\n\n"
            "Return results ordered from most to least relevant."
        )

    def _build_user_prompt_with_budget(
        self, *, query: str, candidates: List[Dict[str, Any]]
    ) -> tuple[List[Dict[str, Any]], str]:
        MAX_CONTEXT_TOKENS = 125_000
        SAFETY_TOKENS = 2_000

        def estimate_tokens(text: str) -> int:
            try:
                return int(len(text) / 4)
            except Exception:
                return int(float(len(text)) / 4)

        def fmt_single(item: Dict[str, Any]) -> str:
            try:
                return (
                    f"[{item['index']}] Source: {item['source']}, Title: {item['title']}\n"
                    f"Content: {item['content']}\n"
                    f"Original Score: {item.get('score', 0):.3f}"
                )
            except Exception:
                return str(item)

        system_prompt = self._build_system_prompt()
        header = f"Query: {query}\n\nSearch Results:\n"
        footer = "\n\nPlease rerank these results from most to least relevant to the query."
        static_tokens = (
            estimate_tokens(system_prompt) + estimate_tokens(header) + estimate_tokens(footer)
        )

        chosen: List[Dict[str, Any]] = []
        running = static_tokens
        for idx, item in enumerate(candidates):
            part = fmt_single(item)
            sep = estimate_tokens("\n\n") if idx > 0 else 0
            need = estimate_tokens(part) + sep
            if running + need + SAFETY_TOKENS <= MAX_CONTEXT_TOKENS:
                chosen.append(item)
                running += need
            else:
                break

        if not chosen and candidates:
            first = fmt_single(candidates[0])
            if static_tokens + estimate_tokens(first) + SAFETY_TOKENS <= MAX_CONTEXT_TOKENS:
                chosen = [candidates[0]]

        formatted = self._format_results_for_prompt(chosen) if chosen else ""
        user_prompt = f"{header}{formatted}{footer}"
        return chosen, user_prompt

    def _log_prompt_stats(
        self, logger: Any, system_prompt: str, user_prompt: str, chosen_count: int
    ) -> None:
        try:
            total_chars = len(system_prompt) + len(user_prompt)
            estimated_tokens = total_chars / 4
            logger.debug(
                f"\n\n[{self.name}] Estimated input tokens: ~{estimated_tokens:.0f} "
                f"(system={len(system_prompt)}, user={len(user_prompt)}, "
                f"candidates={chosen_count})\n\n"
            )
        except Exception:
            pass

    async def _call_groq_structured(
        self,
        client: Any,
        system_prompt: str,
        user_prompt: str,
        RerankedResults: Any,
        logger: Any,
    ) -> tuple[List[Dict[str, Any]], Any]:
        logger.debug(f"\n\n[{self.name}] Calling Groq Structured Outputs\n\n")
        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "reranked_results",
                    "schema": RerankedResults.model_json_schema(),
                },
            },
        )
        logger.debug(f"\n\n[{self.name}] Groq Structured Outputs response: {response}\n\n")
        content = None
        try:
            content = response.choices[0].message.content  # type: ignore
        except Exception:
            content = None

        if not (isinstance(content, str) and content.strip()):
            raise RuntimeError("LLMReranking produced no structured output")

        try:
            obj = _json.loads(content)
            parsed = RerankedResults.model_validate(obj)
        except Exception as je:
            raise RuntimeError(f"LLMReranking failed to parse structured output: {je}")

        if not getattr(parsed, "rankings", None):
            raise RuntimeError("LLMReranking returned empty rankings")

        rankings_list: List[Dict[str, Any]] = [
            {"index": r.index, "relevance_score": r.relevance_score} for r in parsed.rankings
        ]
        return rankings_list, parsed

    def _apply_ranking(
        self, *, results: List[Dict[str, Any]], reranked: Any, limit: int
    ) -> List[Dict[str, Any]]:
        final_results: List[Dict[str, Any]] = []
        ranked_indices = set()
        for ranked_item in reranked.rankings:
            if not isinstance(ranked_item.index, int) or ranked_item.index < 0:
                raise RuntimeError("LLMReranking provided invalid index")
            if ranked_item.index >= len(results):
                raise RuntimeError("LLMReranking index out of bounds")
            final_results.append(results[ranked_item.index])
            ranked_indices.add(ranked_item.index)

        for i, result in enumerate(results):
            if i not in ranked_indices and len(final_results) < limit:
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
