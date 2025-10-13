"""Search factory."""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from airweave import crud
from airweave.api.context import ApiContext
from airweave.core import credentials
from airweave.core.config import settings
from airweave.platform.destinations.collection_strategy import get_default_vector_size
from airweave.platform.locator import resource_locator
from airweave.platform.sources._base import BaseSource
from airweave.platform.sync.token_manager import TokenManager
from airweave.schemas.search import SearchDefaults, SearchRequest
from airweave.search.context import SearchContext
from airweave.search.emitter import EventEmitter
from airweave.search.helpers import search_helpers
from airweave.search.operations import (
    EmbedQuery,
    FederatedSearch,
    GenerateAnswer,
    QueryExpansion,
    QueryInterpretation,
    Reranking,
    Retrieval,
    TemporalRelevance,
    UserFilter,
)
from airweave.search.providers._base import BaseProvider
from airweave.search.providers.cerebras import CerebrasProvider
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

    async def build(
        self,
        request_id: str,
        collection_id: UUID,
        readable_collection_id: str,
        search_request: SearchRequest,
        stream: bool,
        ctx: ApiContext,
        db: AsyncSession,
    ) -> SearchContext:
        """Build SearchContext from request with validated YAML defaults."""
        if not search_request.query or not search_request.query.strip():
            raise HTTPException(status_code=422, detail="Query is required")

        # Apply defaults and validate parameters
        params = self._apply_defaults_and_validate(search_request)

        # Get collection sources
        collection = await crud.collection.get(db, id=collection_id, ctx=ctx)
        federated_sources = await self.get_federated_sources(db, collection, ctx)
        has_federated_sources = bool(federated_sources)
        has_vector_sources = await self._has_vector_sources(db, collection, ctx)

        self._log_source_modes(ctx, federated_sources, has_vector_sources)

        if not has_federated_sources and not has_vector_sources:
            raise ValueError("Collection has no sources")

        # Select providers for operations
        api_keys = self._get_available_api_keys()
        providers = self._create_provider_for_each_operation(
            api_keys, params, has_federated_sources, has_vector_sources, ctx
        )

        # Create event emitter and emit skip notices if needed
        emitter = EventEmitter(request_id=request_id, stream=stream)
        await self._emit_skip_notices_if_needed(emitter, has_vector_sources, params, search_request)

        # Build operations
        vector_size = get_default_vector_size()

        operations = self._build_operations(
            params, providers, federated_sources, has_vector_sources, search_request
        )

        search_context = SearchContext(
            request_id=request_id,
            collection_id=collection_id,
            readable_collection_id=readable_collection_id,
            stream=stream,
            vector_size=vector_size,
            offset=params["offset"],
            limit=params["limit"],
            emitter=emitter,
            query=search_request.query,
            **operations,
        )

        self._log_search_context(ctx, request_id, collection_id, stream, search_request, params)
        ctx.logger.info(
            f"[SearchFactory] Mode summary: has_federated={has_federated_sources}, "
            f"has_vector={has_vector_sources}"
        )

        return search_context

    def _apply_defaults_and_validate(self, search_request: SearchRequest) -> Dict[str, Any]:
        """Apply defaults to search request and validate parameters."""
        retrieval_strategy = (
            search_request.retrieval_strategy
            if search_request.retrieval_strategy is not None
            else defaults.retrieval_strategy
        )
        offset = search_request.offset if search_request.offset is not None else defaults.offset
        limit = search_request.limit if search_request.limit is not None else defaults.limit

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

        if not (0 <= temporal_weight <= 1):
            raise HTTPException(
                status_code=422, detail="temporal_relevance must be between 0 and 1"
            )

        return {
            "retrieval_strategy": retrieval_strategy,
            "offset": offset,
            "limit": limit,
            "expand_query": expand_query,
            "interpret_filters": interpret_filters,
            "rerank": rerank,
            "generate_answer": generate_answer,
            "temporal_weight": temporal_weight,
        }

    def _log_source_modes(self, ctx: ApiContext, federated_sources: List, has_vector_sources: bool):
        """Log information about source modes."""
        try:
            federated_classes = [s.__class__.__name__ for s in federated_sources]
            ctx.logger.info(
                f"[SearchFactory] Federated sources (n={len(federated_classes)}): "
                f"{federated_classes}"
            )
        except Exception:
            pass
        ctx.logger.info(f"[SearchFactory] Vector-backed sources present: {has_vector_sources}")

    def _get_vector_size(self) -> int:
        """Get the default vector size for embeddings."""
        from airweave.platform.destinations.collection_strategy import get_default_vector_size

        return get_default_vector_size()

    async def _emit_skip_notices_if_needed(
        self,
        emitter: EventEmitter,
        has_vector_sources: bool,
        params: Dict[str, Any],
        search_request: SearchRequest,
    ):
        """Emit skip notices for Qdrant-only features when no vector sources exist."""
        if has_vector_sources:
            return

        try:
            if params["interpret_filters"]:
                await emitter.emit(
                    "operation_skipped",
                    {
                        "operation": "QueryInterpretation",
                        "reason": "All sources in the collection use federated search",
                    },
                )
            if search_request.filter is not None:
                await emitter.emit(
                    "operation_skipped",
                    {
                        "operation": "UserFilter",
                        "reason": "All sources in the collection use federated search",
                    },
                )
            if params["temporal_weight"] > 0:
                await emitter.emit(
                    "operation_skipped",
                    {
                        "operation": "TemporalRelevance",
                        "reason": "All sources in the collection use federated search",
                    },
                )
        except Exception:
            raise ValueError("Failed to emit skip notices for Qdrant-only features")

    def _build_operations(
        self,
        params: Dict[str, Any],
        providers: Dict[str, BaseProvider],
        federated_sources: List[BaseSource],
        has_vector_sources: bool,
        search_request: SearchRequest,
    ) -> Dict[str, Any]:
        """Build operation instances for the search context."""
        return {
            "query_expansion": (
                QueryExpansion(provider=providers["expansion"]) if params["expand_query"] else None
            ),
            "query_interpretation": (
                QueryInterpretation(provider=providers["interpretation"])
                if (params["interpret_filters"] and has_vector_sources)
                else None
            ),
            "embed_query": (
                EmbedQuery(
                    strategy=params["retrieval_strategy"],
                    provider=providers["embed"],
                )
                if has_vector_sources
                else None
            ),
            "temporal_relevance": (
                TemporalRelevance(weight=params["temporal_weight"])
                if (params["temporal_weight"] > 0 and has_vector_sources)
                else None
            ),
            "user_filter": (
                UserFilter(filter=search_request.filter)
                if (search_request.filter and has_vector_sources)
                else None
            ),
            "retrieval": (
                Retrieval(
                    strategy=params["retrieval_strategy"],
                    offset=params["offset"],
                    limit=params["limit"],
                )
                if has_vector_sources
                else None
            ),
            "federated_search": (
                FederatedSearch(
                    sources=federated_sources,
                    limit=params["limit"],
                    provider=providers["federated"],
                )
                if federated_sources
                else None
            ),
            "reranking": Reranking(provider=providers["rerank"]) if params["rerank"] else None,
            "generate_answer": (
                GenerateAnswer(provider=providers["answer"]) if params["generate_answer"] else None
            ),
        }

    def _log_search_context(
        self,
        ctx: ApiContext,
        request_id: str,
        collection_id: UUID,
        stream: bool,
        search_request: SearchRequest,
        params: Dict[str, Any],
    ):
        """Log search context configuration."""
        ctx.logger.debug(
            f"[SearchFactory] Built search context: \n"
            f"request_id={request_id}, \n"
            f"collection_id={collection_id}, \n"
            f"stream={stream}, \n"
            f"query='{search_request.query[:50]}...', \n"
            f"retrieval_strategy={params['retrieval_strategy']}, \n"
            f"offset={params['offset']}, \n"
            f"limit={params['limit']}, "
            f"temporal_weight={params['temporal_weight']}, \n"
            f"expand_query={params['expand_query']}, \n"
            f"interpret_filters={params['interpret_filters']}, \n"
            f"rerank={params['rerank']}, \n"
            f"generate_answer={params['generate_answer']}, \n"
        )

    def _get_available_api_keys(self) -> Dict[str, Optional[str]]:
        """Get available API keys from settings."""
        return {
            "cerebras": getattr(settings, "CEREBRAS_API_KEY", None),
            "groq": getattr(settings, "GROQ_API_KEY", None),
            "openai": getattr(settings, "OPENAI_API_KEY", None),
            "cohere": getattr(settings, "COHERE_API_KEY", None),
        }

    def _create_provider_for_each_operation(
        self,
        api_keys: Dict[str, Optional[str]],
        params: Dict[str, Any],
        has_federated_sources: bool,
        has_vector_sources: bool,
        ctx: ApiContext,
    ) -> Dict[str, BaseProvider]:
        """Select and validate all required providers."""
        providers = {}

        # Create embedding provider if needed
        if has_vector_sources:
            providers["embed"] = self._create_embedding_provider(api_keys, ctx)

        # Create LLM providers for enabled operations
        providers.update(
            self._create_llm_providers(
                api_keys, params, has_federated_sources, has_vector_sources, ctx
            )
        )

        ctx.logger.debug(f"[SearchFactory] Providers: {providers}")
        return providers

    def _create_embedding_provider(
        self, api_keys: Dict[str, Optional[str]], ctx: ApiContext
    ) -> BaseProvider:
        """Create embedding provider for vector-backed search."""
        provider = self._init_provider_with_model_spec("embed_query", api_keys, ctx)
        if not provider:
            raise ValueError(
                "Embedding provider required for vector-backed search. Configure OPENAI_API_KEY"
            )
        return provider

    def _create_llm_providers(
        self,
        api_keys: Dict[str, Optional[str]],
        params: Dict[str, Any],
        has_federated_sources: bool,
        has_vector_sources: bool,
        ctx: ApiContext,
    ) -> Dict[str, BaseProvider]:
        """Create LLM providers for enabled operations."""
        providers = {}

        # Query expansion
        if params["expand_query"]:
            self._add_provider_or_error(
                providers,
                "expansion",
                "query_expansion",
                api_keys,
                ctx,
                "Query expansion enabled but no provider available. "
                "Configure CEREBRAS_API_KEY, GROQ_API_KEY, or OPENAI_API_KEY",
            )

        # Federated search
        if has_federated_sources:
            self._add_provider_or_error(
                providers,
                "federated",
                "federated_search",
                api_keys,
                ctx,
                "Federated sources exist but no provider available for keyword extraction. "
                "Configure CEREBRAS_API_KEY, GROQ_API_KEY, or OPENAI_API_KEY",
            )

        # Query interpretation
        if params["interpret_filters"] and has_vector_sources:
            self._add_provider_or_error(
                providers,
                "interpretation",
                "query_interpretation",
                api_keys,
                ctx,
                "Query interpretation enabled but no provider available. "
                "Configure CEREBRAS_API_KEY, GROQ_API_KEY, or OPENAI_API_KEY",
            )

        # Reranking
        if params["rerank"]:
            self._add_provider_or_error(
                providers,
                "rerank",
                "reranking",
                api_keys,
                ctx,
                "Reranking enabled but no provider available. "
                "Configure COHERE_API_KEY, GROQ_API_KEY, or OPENAI_API_KEY",
            )

        # Answer generation
        if params["generate_answer"]:
            self._add_provider_or_error(
                providers,
                "answer",
                "generate_answer",
                api_keys,
                ctx,
                "Answer generation enabled but no provider available. "
                "Configure CEREBRAS_API_KEY, GROQ_API_KEY, or OPENAI_API_KEY",
            )

        return providers

    def _add_provider_or_error(
        self,
        providers: Dict[str, BaseProvider],
        key: str,
        operation_name: str,
        api_keys: Dict[str, Optional[str]],
        ctx: ApiContext,
        error_message: str,
    ):
        """Add a provider to the dict or raise an error if unavailable."""
        provider = self._init_provider_with_model_spec(operation_name, api_keys, ctx)
        if not provider:
            raise ValueError(error_message)
        providers[key] = provider

    async def _has_vector_sources(self, db: AsyncSession, collection, ctx: ApiContext) -> bool:
        """Return True if collection has any non-federated (vector-backed) sources."""
        try:
            source_connections = await crud.source_connection.get_for_collection(
                db, readable_collection_id=collection.readable_id, ctx=ctx
            )
            if not source_connections:
                return False

            for source_connection in source_connections:
                source_model = await crud.source.get_by_short_name(db, source_connection.short_name)
                if not source_model:
                    raise ValueError(f"Source model not found for {source_connection.short_name}")
                source_class = resource_locator.get_source(source_model)
                if not getattr(source_class, "_federated_search", False):
                    return True
            return False
        except Exception:
            raise ValueError(
                f"Error getting vector sources for collection {collection.readable_id}"
            )

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
                if provider_name == "cerebras":
                    ctx.logger.debug(
                        f"[Factory] Attempting to initialize CerebrasProvider for {operation_name}"
                    )
                    return CerebrasProvider(api_key=api_key, model_spec=model_spec, ctx=ctx)
                elif provider_name == "groq":
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

    async def get_federated_sources(
        self, db: AsyncSession, collection, ctx: ApiContext
    ) -> List[BaseSource]:
        """Get instantiated federated sources for a collection.

        Args:
            db: Database session
            collection: Collection object
            ctx: API context

        Returns:
            List of instantiated source objects that support federated search
        """
        try:
            source_connections = await crud.source_connection.get_for_collection(
                db, readable_collection_id=collection.readable_id, ctx=ctx
            )

            if not source_connections:
                return []

            federated_sources = []
            for source_connection in source_connections:
                source_instance = await self._try_instantiate_federated_source(
                    db, source_connection, ctx
                )
                if source_instance:
                    federated_sources.append(source_instance)

            return federated_sources

        except Exception as e:
            raise ValueError(f"Error getting federated sources: {e}")

    async def _try_instantiate_federated_source(
        self, db: AsyncSession, source_connection, ctx: ApiContext
    ) -> Optional[BaseSource]:
        """Try to instantiate a federated source from a source connection."""
        try:
            # Check if source supports federated search
            source_model = await crud.source.get_by_short_name(db, source_connection.short_name)
            if not source_model:
                ctx.logger.warning(f"Source model not found for {source_connection.short_name}")
                return None

            source_class = resource_locator.get_source(source_model)
            if not getattr(source_class, "_federated_search", False):
                return None

            ctx.logger.info(
                f"Found federated source: {source_connection.short_name} "
                f"(id: {source_connection.id})"
            )

            # Get credentials and create source instance
            credentials_data = await self._get_source_credentials(db, source_connection, ctx)
            source_instance = await source_class.create(
                credentials_data["access_token"], config=source_connection.config_fields
            )

            # Configure source instance
            if hasattr(source_instance, "set_logger"):
                source_instance.set_logger(ctx.logger)

            # Setup token manager if needed
            if source_model.oauth_type and isinstance(credentials_data["decrypted"], dict):
                self._setup_token_manager(
                    source_instance,
                    db,
                    source_connection,
                    credentials_data["connection"],
                    credentials_data["decrypted"],
                    ctx,
                )

            ctx.logger.info(
                f"Successfully instantiated federated source: {source_connection.short_name}"
            )
            return source_instance

        except Exception as e:
            raise ValueError(
                f"Error instantiating federated source {source_connection.short_name}: {e}"
            )

    async def _get_source_credentials(
        self, db: AsyncSession, source_connection, ctx: ApiContext
    ) -> Dict[str, Any]:
        """Get and decrypt credentials for a source connection."""
        connection = await crud.connection.get(db, source_connection.connection_id, ctx)
        if not connection or not connection.integration_credential_id:
            raise ValueError(f"No credentials found for source connection {source_connection.id}")

        credential = await crud.integration_credential.get(
            db, connection.integration_credential_id, ctx
        )
        if not credential:
            raise ValueError(f"No credentials found for source connection {source_connection.id}")

        decrypted_credential = credentials.decrypt(credential.encrypted_credentials)

        # Extract access token
        access_token = None
        if isinstance(decrypted_credential, dict):
            access_token = decrypted_credential.get("access_token")
        elif isinstance(decrypted_credential, str):
            access_token = decrypted_credential

        if not access_token:
            raise ValueError(f"No access token found for source {source_connection.short_name}")

        return {
            "access_token": access_token,
            "decrypted": decrypted_credential,
            "connection": connection,
        }

    def _setup_token_manager(
        self,
        source_instance: BaseSource,
        db: AsyncSession,
        source_connection,
        connection,
        decrypted_credential: dict,
        ctx: ApiContext,
    ):
        """Setup token manager for OAuth sources."""
        minimal_connection = type(
            "MinimalConnection",
            (),
            {
                "id": connection.id,
                "integration_credential_id": connection.integration_credential_id,
                "config_fields": source_connection.config_fields,
            },
        )()

        token_manager = TokenManager(
            db=db,
            source_short_name=source_connection.short_name,
            source_connection=minimal_connection,
            ctx=ctx,
            initial_credentials=decrypted_credential,
            is_direct_injection=False,
            logger_instance=ctx.logger,
        )
        source_instance.set_token_manager(token_manager)


factory = SearchFactory()
