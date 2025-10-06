"""Query expansion operation.

Expands the user's query into multiple variations to improve recall.
Uses LLM to generate semantic alternatives that might match relevant documents
using different terminology while preserving the original search intent.
"""

from typing import Any, List

from pydantic import BaseModel, Field

from airweave.api.context import ApiContext
from airweave.search.context import SearchContext
from airweave.search.prompts import QUERY_EXPANSION_SYSTEM_PROMPT
from airweave.search.providers._base import BaseProvider

from ._base import SearchOperation


class QueryExpansions(BaseModel):
    """Structured output schema for LLM-generated query expansions."""

    alternatives: List[str] = Field(
        description="Alternative query phrasings",
        max_length=4,
    )


class QueryExpansion(SearchOperation):
    """Expand user query into multiple variations for better recall."""

    MAX_EXPANSIONS = 4

    def __init__(self, provider: BaseProvider) -> None:
        """Initialize with LLM provider.

        Args:
            provider: LLM provider for structured output (guaranteed by factory)
        """
        self.provider = provider

    def depends_on(self) -> List[str]:
        """No dependencies - runs first if enabled."""
        return []

    async def execute(self, context: SearchContext, state: dict[str, Any], ctx: ApiContext) -> None:
        """Expand the query into variations."""
        ctx.logger.debug("[QueryExpansion] Expanding the query into variations")

        query = context.query

        # Validate query length before sending to LLM
        self._validate_query_length(query, ctx)

        # Build prompts
        system_prompt = QUERY_EXPANSION_SYSTEM_PROMPT.format(max_expansions=self.MAX_EXPANSIONS)
        user_prompt = f"Original query: {query}"

        # Get structured output from provider
        result = await self.provider.structured_output(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            schema=QueryExpansions,
        )

        # Validate and deduplicate alternatives
        alternatives = result.alternatives or []
        valid_alternatives = self._validate_alternatives(alternatives, query)
        ctx.logger.debug(f"[QueryExpansion] Valid alternatives: {valid_alternatives}")

        # Ensure we got exactly the expected number of alternatives
        if len(valid_alternatives) != self.MAX_EXPANSIONS:
            raise ValueError(
                f"Query expansion failed: expected exactly {self.MAX_EXPANSIONS} alternatives, "
                f"got {len(valid_alternatives)}. LLM returned wrong number of valid alternatives."
            )

        # Write alternatives to state (original query remains in context.query)
        state["expanded_queries"] = valid_alternatives

    def _validate_query_length(self, query: str, ctx: ApiContext) -> None:
        """Validate query fits in provider's context window."""
        # Get LLM tokenizer from provider
        tokenizer = getattr(self.provider, "llm_tokenizer", None)
        if not tokenizer:
            provider_name = self.provider.__class__.__name__
            raise RuntimeError(
                f"Provider {provider_name} does not have an LLM tokenizer. "
                "Cannot validate query length."
            )

        token_count = self.provider.count_tokens(query, tokenizer)
        ctx.logger.debug(f"[QueryExpansion] Token count: {token_count}")

        # Estimate prompt overhead: system prompt ~500 tokens, structured output ~500 tokens
        prompt_overhead = 1000
        max_allowed = self.provider.model_spec.llm_model.context_window - prompt_overhead

        if token_count > max_allowed:
            raise ValueError(
                f"Query too long: {token_count} tokens exceeds max of {max_allowed} "
                f"for query expansion"
            )

    def _validate_alternatives(self, alternatives: List[str], original_query: str) -> List[str]:
        """Validate and clean alternatives from LLM."""
        valid = []

        for alt in alternatives:
            if not isinstance(alt, str) or not alt.strip():
                continue

            cleaned = alt.strip()

            # Skip if same as original (case-insensitive)
            if cleaned.lower() == original_query.lower():
                continue

            # Skip duplicates
            if cleaned not in valid:
                valid.append(cleaned)

        return valid
