"""Query expansion operation.

This operation expands the user's query into multiple variations to improve
recall. As of this version, the operation no longer supports streaming
structured outputs. Both streaming and non-streaming searches use the
same non-streaming structured output path. In streaming mode, we still
emit basic lifecycle events (expansion_start, expansion_done), but no
incremental "delta" events.
"""

import json as _json
from typing import Any, Dict, List, Optional

from groq import AsyncGroq

from airweave.core.config import settings
from airweave.schemas.search import QueryExpansions, QueryExpansionStrategy
from airweave.search.operations.base import SearchOperation


class QueryExpansions(BaseModel):
    """Structured output for LLM-based query expansions."""

    alternatives: List[str] = Field(
        ...,
        description="Alternative query phrasings",
        max_length=4,
    )


class QueryExpansion(SearchOperation):
    """Expands a query into multiple variations.

    This operation takes the original query and generates variations
    that might match relevant documents using different terminology.
    The expanded queries are then embedded and searched in parallel.

    Example:
        Input: "customer payment issues"
        Output: ["customer payment issues", "billing problems",
                 "payment failures", "transaction errors"]
    """

    def __init__(self, strategy: str = "auto", max_expansions: int = 4):
        """Initialize query expansion operation.

        Args:
            strategy: Expansion strategy ("auto", "llm", "none")
            max_expansions: Maximum number of query variations to generate
        """
        self.strategy = strategy
        self.max_expansions = max_expansions
        self._groq_client = None

    @property
    def name(self) -> str:
        """Operation name."""
        return "query_expansion"

    @property
    def groq_client(self) -> Optional[AsyncGroq]:
        """Lazy-load Groq async client.

        Returns:
            AsyncGroq: The Groq client. Requires GROQ_API_KEY via env.
        """
        if self._groq_client is None and settings.GROQ_API_KEY:
            # AsyncGroq reads GROQ_API_KEY from env; no need to pass explicitly
            self._groq_client = AsyncGroq()
        return self._groq_client

    async def execute(self, context: Dict[str, Any]) -> None:  # noqa: C901
        """Expand the query into multiple variations.

        Reads from context:
            - query: Original search query
            - config: SearchConfig (for strategy override)
            - logger: For logging

        Writes to context:
            - expanded_queries: List of query variations
        """
        query = context["query"]
        logger = context["logger"]
        config = context["config"]

        # Strategy can be overridden by config
        strategy = (
            config.expansion_strategy if hasattr(config, "expansion_strategy") else self.strategy
        )

        # Convert string strategy to enum if needed
        if isinstance(strategy, str):
            strategy = self._resolve_strategy(strategy)

        logger.debug(f"[QueryExpansion] Expanding query using strategy: {strategy}")

        # If in streaming mode, emit a basic start event (no deltas)
        emitter = context.get("emit")
        request_id = context.get("request_id")
        if request_id and callable(emitter):
            try:
                model = "gpt-5-nano" if strategy == QueryExpansionStrategy.LLM else None
                await emitter(
                    "expansion_start",
                    {"model": model, "strategy": ("llm" if model else "none")},
                    op_name=self.name,
                )
            except Exception:
                pass

        try:
            # Single non-streaming path for both streaming and non-streaming searches
            expanded_queries = await self._expand(query, strategy, logger)

            # Limit the number of expansions
            if len(expanded_queries) > self.max_expansions:
                expanded_queries = expanded_queries[: self.max_expansions]
                logger.debug(f"[QueryExpansion] Limited expansions to {self.max_expansions}")

            context["expanded_queries"] = expanded_queries
            logger.debug(
                (
                    f"[QueryExpansion] Expanded query '{query[:50]}...' to "
                    f"{len(expanded_queries)} variations"
                )
            )

            if logger.isEnabledFor(10):  # DEBUG level
                logger.debug(f"[QueryExpansion] Variations: {expanded_queries}")

            # In streaming mode, emit a done event with the final alternatives
            if request_id and callable(emitter):
                try:
                    await emitter(
                        "expansion_done", {"alternatives": expanded_queries}, op_name=self.name
                    )
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"[QueryExpansion] Failed: {e}", exc_info=True)
            # Propagate error so executor can fail the search
            if request_id and callable(emitter):
                try:
                    await emitter(
                        "error", {"operation": self.name, "message": str(e)}, op_name=self.name
                    )
                except Exception:
                    pass
            raise

    def _resolve_strategy(self, requested: str | QueryExpansionStrategy) -> QueryExpansionStrategy:
        """Resolve the expansion strategy to use.

        Args:
            requested: The requested strategy (enum or string)

        Returns:
            QueryExpansionStrategy: The resolved strategy enum value
        """
        # Convert string to enum if needed
        if isinstance(requested, str):
            try:
                requested = QueryExpansionStrategy(requested.lower())
            except ValueError:
                # Default to AUTO for invalid values
                requested = QueryExpansionStrategy.AUTO

        # Handle AUTO strategy
        if requested == QueryExpansionStrategy.AUTO:
            # Use GROQ key presence to decide LLM availability for expansion
            if getattr(settings, "GROQ_API_KEY", None):
                return QueryExpansionStrategy.LLM
            return QueryExpansionStrategy.NO_EXPANSION

        return requested

    async def _expand(self, query: str, strategy: QueryExpansionStrategy, logger) -> List[str]:
        """Main expansion entry point.

        Args:
            query: The query to expand
            strategy: The strategy to use
            logger: The logger to use
        Returns:
            List of queries with original first
        """
        if strategy == QueryExpansionStrategy.NO_EXPANSION:
            return [query]
        elif strategy == QueryExpansionStrategy.LLM:
            return await self._llm_expand(query, logger)

        # Fallback
        return [query]

    async def _llm_expand(self, query: str, logger) -> List[str]:
        """Use LLM to generate semantically similar search queries.

        Prompts GPT to create alternative phrasings that could retrieve relevant
        passages while maintaining the original search intent.

        Args:
            query: The query to expand
            logger: The logger to use

        Returns:
            List of queries with the original query as the first item
        """
        if not self.groq_client:
            # Fail fast when LLM strategy is selected but client is unavailable
            raise RuntimeError("QueryExpansion LLM client not configured (GROQ_API_KEY missing)")

        try:
            # Generate alternatives using Groq Structured Outputs (non-streaming)
            system_message = self._get_expansion_system_prompt()
            user_message = self._get_expansion_user_prompt(query)

            response = await self.groq_client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "query_expansions",
                        "schema": QueryExpansions.model_json_schema(),
                    },
                },
                max_completion_tokens=2000,
            )

            content = None
            try:
                content = response.choices[0].message.content  # type: ignore
            except Exception:
                content = None

            if not (isinstance(content, str) and content.strip()):
                # Fail fast: LLM did not return structured content
                raise RuntimeError("QueryExpansion received no structured content from LLM")

            try:
                obj = _json.loads(content)
                parsed = QueryExpansions.model_validate(obj)
                logger.debug(f"[QueryExpansion] Structured parse result: {parsed}")
                alternatives: List[str] = parsed.alternatives or []
            except Exception as je:
                # Fail fast on schema/JSON parse errors
                raise RuntimeError(f"QueryExpansion failed to parse structured output: {je}")

            valid_alternatives = self._validate_alternatives(alternatives, query)
            return self._build_expansion_result(query, valid_alternatives)

        except Exception as e:
            # Propagate failure so the executor can fail the search (fail-fast)
            logger.error(f"[QueryExpansion] LLM request failed: {e}")
            raise

    def _get_expansion_system_prompt(self) -> str:
        """Get the system prompt for query expansion."""
        return (
            "You are a search query expansion assistant. Your job is to create "
            "high-quality alternative phrasings that improve recall for a hybrid "
            "keyword + vector search, while preserving the user's intent.\n\n"
            "Core behaviors (optimize recall without changing meaning):\n"
            "- Produce diverse paraphrases that surface different vocabulary and "
            "phrasing.\n"
            "- Include at least one keyword-forward variant (good for BM25).\n"
            "- Include a normalized/literal variant that spells out implicit "
            "constraints (e.g., role/company/location/education if present).\n"
            "- Expand common abbreviations and acronyms to their full forms.\n"
            "- Swap common synonyms and morphological variants "
            "(manage→management, bill→billing).\n"
            "- Recast questions as statements or list intents when appropriate "
            "(e.g., 'find', 'list', 'show').\n"
            "- Do not introduce constraints that are not implied by the query.\n"
            "- Avoid duplicates and near-duplicates (punctuation-only or trivial "
            "reorderings).\n\n"
        )

    def _get_expansion_user_prompt(self, query: str) -> str:
        """Get the user prompt for query expansion."""
        return (
            f"Original query: {query}\n\n"
            f"Instructions:\n"
            f"- Generate up to {self.max_expansions} alternatives that preserve "
            f"intent and increase recall.\n"
            f"- Favor lexical diversity: use synonyms, category names, and "
            f"different grammatical forms.\n"
            f"- Include one keyword-heavy form and one normalized/literal form "
            f"if applicable.\n"
            f"- Expand abbreviations (e.g., 'eng'→'engineering', 'SF'→'San Francisco').\n"
            f"- Avoid adding new constraints; avoid duplicates and trivial "
            f"rephrasings.\n"
        )

    def _validate_alternatives(self, alternatives: list, original_query: str) -> List[str]:
        """Validate and clean the alternatives from OpenAI.

        Args:
            alternatives: Raw alternatives from OpenAI
            original_query: The original query to avoid duplicates

        Returns:
            List of valid, cleaned alternatives
        """
        valid_alternatives = []

        for alt in alternatives:
            if isinstance(alt, str) and alt.strip():
                cleaned = alt.strip()
                # Skip if it's the same as original (case-insensitive)
                if cleaned.lower() != original_query.lower():
                    valid_alternatives.append(cleaned)

        return valid_alternatives

    def _build_expansion_result(
        self, original_query: str, valid_alternatives: List[str]
    ) -> List[str]:
        """Build the final expansion result with original query first.

        Args:
            original_query: The original search query
            valid_alternatives: Validated alternatives

        Returns:
            Final list with original query first, then alternatives
        """
        result = [original_query]

        # Add alternatives up to the limit, avoiding duplicates
        for alt in valid_alternatives[: self.max_expansions]:
            if alt not in result:
                result.append(alt)

        return result
