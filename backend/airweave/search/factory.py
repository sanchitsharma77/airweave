"""Search factory."""

from typing import Dict, Optional
from uuid import UUID

from fastapi import HTTPException

from airweave.api.context import ApiContext
from airweave.core.config import settings
from airweave.schemas.search import SearchDefaults, SearchRequest
from airweave.search.context import SearchContext
from airweave.search.helpers import search_helpers
from airweave.search.operations import (
    EmbedQuery,
    GenerateAnswer,
    QueryExpansion,
    QueryInterpretation,
    Reranking,
    Retrieval,
    TemporalRelevance,
    UserFilter,
)
from airweave.search.providers._base import BaseProvider
from airweave.search.providers.cohere import CohereProvider
from airweave.search.providers.groq import GroqProvider
from airweave.search.providers.openai import OpenAIProvider
from airweave.search.providers.schemas import (
    EmbeddingModelConfig,
    LLMModelConfig,
    ProviderModelSpec,
    RerankModelConfig,
)

# Rebuild SearchContext model now that all operation classes are imported
SearchContext.model_rebuild()

defaults_data = search_helpers.load_defaults()
defaults = SearchDefaults(**defaults_data["search_defaults"])
provider_models = defaults_data.get("provider_models", {})
operation_preferences = defaults_data.get("operation_preferences", {})


class SearchFactory:
    """Create search context with provider-aware operations."""

    def build(
        self,
        request_id: str,
        collection_id: UUID,
        readable_collection_id: str,
        search_request: SearchRequest,
        stream: bool,
        ctx: ApiContext,
    ) -> SearchContext:
        """Build SearchContext from request with validated YAML defaults."""
        if not search_request.query or not search_request.query.strip():
            raise HTTPException(status_code=422, detail="Query is required")

        retrieval_strategy = (
            search_request.retrieval_strategy
            if search_request.retrieval_strategy is not None
            else defaults.retrieval_strategy
        )

        offset = search_request.offset if search_request.offset is not None else defaults.offset
        limit = search_request.limit if search_request.limit is not None else defaults.limit

        # Validate numeric ranges
        if offset < 0:
            raise HTTPException(status_code=422, detail="offset must be >= 0")
        if limit < 1:
            raise HTTPException(status_code=422, detail="limit must be >= 1")

        expand_query = (
            search_request.expand_query
            if search_request.expand_query is not None
            else defaults.expand_query
        )
        interpret_filters = (
            search_request.interpret_filters
            if search_request.interpret_filters is not None
            else defaults.interpret_filters
        )
        rerank = search_request.rerank if search_request.rerank is not None else defaults.rerank
        generate_answer = (
            search_request.generate_answer
            if search_request.generate_answer is not None
            else defaults.generate_answer
        )

        temporal_weight = (
            search_request.temporal_relevance
            if search_request.temporal_relevance is not None
            else defaults.temporal_relevance
        )

        # Validate temporal_relevance range
        if not (0 <= temporal_weight <= 1):
            raise HTTPException(
                status_code=422, detail="temporal_relevance must be between 0 and 1"
            )

        # Select providers for LLM-based operations
        api_keys = self._get_available_api_keys()
        providers = self._create_provider_for_each_operation(
            api_keys, expand_query, interpret_filters, rerank, generate_answer, ctx
        )

        search_context = SearchContext(
            # Metadata
            request_id=request_id,
            collection_id=collection_id,
            readable_collection_id=readable_collection_id,
            stream=stream,
            # Shared static data
            query=search_request.query,
            # Operation instances (execution plan)
            query_expansion=(
                QueryExpansion(provider=providers["expansion"]) if expand_query else None
            ),
            query_interpretation=(
                QueryInterpretation(provider=providers["interpretation"])
                if interpret_filters
                else None
            ),
            embed_query=EmbedQuery(strategy=retrieval_strategy, provider=providers["embed"]),
            temporal_relevance=TemporalRelevance(weight=temporal_weight)
            if temporal_weight > 0
            else None,
            user_filter=UserFilter(filter=search_request.filter) if search_request.filter else None,
            retrieval=Retrieval(strategy=retrieval_strategy, offset=offset, limit=limit),
            reranking=Reranking(provider=providers["rerank"]) if rerank else None,
            generate_answer=(
                GenerateAnswer(provider=providers["answer"]) if generate_answer else None
            ),
        )

        # Log search context configuration
        ctx.logger.debug(
            f"[SearchFactory] Built search context: \n"
            f"request_id={request_id}, \n"
            f"collection_id={collection_id}, \n"
            f"stream={stream}, \n"
            f"query='{search_request.query[:50]}...', \n"
            f"retrieval_strategy={retrieval_strategy}, \n"
            f"offset={offset}, \n"
            f"limit={limit}, "
            f"temporal_weight={temporal_weight}, \n"
            f"expand_query={expand_query}, \n"
            f"interpret_filters={interpret_filters}, \n"
            f"rerank={rerank}, \n"
            f"generate_answer={generate_answer}, \n"
        )

        return search_context

    def _get_available_api_keys(self) -> Dict[str, Optional[str]]:
        """Get available API keys from settings."""
        return {
            "groq": getattr(settings, "GROQ_API_KEY", None),
            "openai": getattr(settings, "OPENAI_API_KEY", None),
            "cohere": getattr(settings, "COHERE_API_KEY", None),
        }

    def _create_provider_for_each_operation(
        self,
        api_keys: Dict[str, Optional[str]],
        expand_query: bool,
        interpret_filters: bool,
        rerank: bool,
        generate_answer: bool,
        ctx: ApiContext,
    ) -> Dict[str, BaseProvider]:
        """Select and validate all required providers."""
        providers = {}

        # Embedding provider (always required)
        providers["embed"] = self._init_provider_with_model_spec("embed_query", api_keys, ctx)
        if not providers["embed"]:
            raise ValueError("Embedding provider required. Configure OPENAI_API_KEY")

        # Query expansion provider (required if enabled)
        if expand_query:
            providers["expansion"] = self._init_provider_with_model_spec(
                "query_expansion", api_keys, ctx
            )
            if not providers["expansion"]:
                raise ValueError(
                    "Query expansion enabled but no provider available. "
                    "Configure GROQ_API_KEY or OPENAI_API_KEY"
                )

        # Query interpretation provider (required if enabled)
        if interpret_filters:
            providers["interpretation"] = self._init_provider_with_model_spec(
                "query_interpretation", api_keys, ctx
            )
            if not providers["interpretation"]:
                raise ValueError(
                    "Query interpretation enabled but no provider available. "
                    "Configure GROQ_API_KEY or OPENAI_API_KEY"
                )

        # Reranking provider (required if enabled)
        if rerank:
            providers["rerank"] = self._init_provider_with_model_spec("reranking", api_keys, ctx)
            if not providers["rerank"]:
                raise ValueError(
                    "Reranking enabled but no provider available. "
                    "Configure COHERE_API_KEY, GROQ_API_KEY, or OPENAI_API_KEY"
                )

        # Answer generation provider (required if enabled)
        if generate_answer:
            providers["answer"] = self._init_provider_with_model_spec(
                "generate_answer", api_keys, ctx
            )
            if not providers["answer"]:
                raise ValueError(
                    "Answer generation enabled but no provider available. "
                    "Configure GROQ_API_KEY or OPENAI_API_KEY"
                )

        ctx.logger.debug(f"[SearchFactory] Providers: {providers}")
        return providers

    def _init_provider_with_model_spec(
        self, operation_name: str, api_keys: Dict[str, Optional[str]], ctx: ApiContext
    ) -> Optional[BaseProvider]:
        """Select and initialize provider for an operation."""
        preferences = operation_preferences.get(operation_name, {})
        order = preferences.get("order", [])

        # Try each provider in preference order
        for entry in order:
            provider_name = entry.get("provider")
            if not provider_name:
                # Skip malformed entries
                continue

            api_key = api_keys.get(provider_name)
            if not api_key:
                # API key not available for this provider, try next in fallback order
                continue

            # Get provider's model specifications
            provider_spec = provider_models.get(provider_name, {})

            # Build model configs for each type
            llm_config = self._build_llm_config(provider_spec, entry.get("llm"))
            embedding_config = self._build_embedding_config(provider_spec, entry.get("embedding"))
            rerank_config = self._build_rerank_config(provider_spec, entry.get("rerank"))

            model_spec = ProviderModelSpec(
                llm_model=llm_config,
                embedding_model=embedding_config,
                rerank_model=rerank_config,
            )

            # Initialize provider with complete model spec
            try:
                if provider_name == "groq":
                    ctx.logger.debug(
                        f"[Factory] Attempting to initialize GroqProvider for {operation_name}"
                    )
                    return GroqProvider(api_key=api_key, model_spec=model_spec, ctx=ctx)
                elif provider_name == "openai":
                    ctx.logger.debug(
                        f"[Factory] Attempting to initialize OpenAIProvider for {operation_name}"
                    )
                    return OpenAIProvider(api_key=api_key, model_spec=model_spec, ctx=ctx)
                elif provider_name == "cohere":
                    ctx.logger.debug(
                        f"[Factory] Attempting to initialize CohereProvider for {operation_name}"
                    )
                    return CohereProvider(api_key=api_key, model_spec=model_spec, ctx=ctx)
            except Exception as e:
                # Provider initialization failed (bad API key, missing tokenizer, etc.)
                # Try next provider in fallback order
                ctx.logger.warning(
                    f"[Factory] Failed to initialize {provider_name} for {operation_name}: {e}"
                )
                continue

        # No provider available with valid API key and configuration
        return None

    def _build_llm_config(
        self, provider_spec: dict, model_key: Optional[str]
    ) -> Optional[LLMModelConfig]:
        """Build LLMModelConfig from provider spec."""
        if not model_key:
            return None

        model_dict = provider_spec.get(model_key)
        if not model_dict:
            return None

        return LLMModelConfig(**model_dict)

    def _build_embedding_config(
        self, provider_spec: dict, model_key: Optional[str]
    ) -> Optional[EmbeddingModelConfig]:
        """Build EmbeddingModelConfig from provider spec."""
        if not model_key:
            return None

        model_dict = provider_spec.get(model_key)
        if not model_dict:
            return None

        return EmbeddingModelConfig(**model_dict)

    def _build_rerank_config(
        self, provider_spec: dict, model_key: Optional[str]
    ) -> Optional[RerankModelConfig]:
        """Build RerankModelConfig from provider spec."""
        if not model_key:
            return None

        model_dict = provider_spec.get(model_key)
        if not model_dict:
            return None

        return RerankModelConfig(**model_dict)


factory = SearchFactory()
