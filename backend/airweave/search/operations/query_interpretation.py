"""Query interpretation operation.

Uses LLM to interpret natural language queries and extract structured Qdrant filters.
Enables users to filter results using natural language without knowing filter syntax.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from airweave import crud
from airweave.api.context import ApiContext
from airweave.db.session import get_db_context
from airweave.search.context import SearchContext
from airweave.search.prompts import QUERY_INTERPRETATION_SYSTEM_PROMPT
from airweave.search.providers._base import BaseProvider

from ._base import SearchOperation


class FilterCondition(BaseModel):
    """A single filter condition."""

    key: str
    match: Optional[Dict[str, Any]] = None
    range: Optional[Dict[str, Any]] = None


class ExtractedFilters(BaseModel):
    """Structured output schema for extracted filters."""

    filters: List[FilterCondition] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class QueryInterpretation(SearchOperation):
    """Extract structured Qdrant filters from natural language query."""

    CONFIDENCE_THRESHOLD = 0.7

    # System metadata fields that are stored in airweave_system_metadata nested object
    # These need to be mapped from simple names to nested paths for Qdrant
    NESTED_SYSTEM_FIELDS = {
        "source_name": "Source connector name (case-sensitive)",
        "entity_type": "Entity type name",
        "sync_id": "Sync ID (UUID, for debugging)",
        "airweave_created_at": "Created in Airweave (ISO8601 datetime)",
        "airweave_updated_at": "Last updated in Airweave (ISO8601 datetime)",
    }

    def __init__(self, provider: BaseProvider) -> None:
        """Initialize with LLM provider."""
        self.provider = provider

    def depends_on(self) -> List[str]:
        """Depends on query expansion to get all query variations."""
        return ["QueryExpansion"]

    async def execute(self, context: SearchContext, state: dict[str, Any], ctx: ApiContext) -> None:
        """Extract filters from query using LLM."""
        ctx.logger.debug("[QueryInterpretation] Extracting filters from query")

        query = context.query
        expanded_queries = state.get("expanded_queries", [])

        # Discover available fields for this collection
        available_fields = await self._discover_fields(context.collection_id)
        ctx.logger.debug(f"[QueryInterpretation] Available fields: {available_fields}")

        # Build prompts
        system_prompt = self._build_system_prompt(available_fields)
        ctx.logger.debug(f"[QueryInterpretation] System prompt: {system_prompt}")
        user_prompt = self._build_user_prompt(query, expanded_queries)

        # Validate prompt length
        self._validate_prompt_length(system_prompt, user_prompt)

        # Get structured output from provider
        result = await self.provider.structured_output(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            schema=ExtractedFilters,
        )

        # Check confidence threshold
        if result.confidence < self.CONFIDENCE_THRESHOLD:
            ctx.logger.debug(f"[QueryInterpretation] Low confidence: {result.confidence}")
            # Low confidence - don't apply filters
            return

        # Validate and map filter conditions
        validated_filters = self._validate_filters(result.filters, available_fields)
        ctx.logger.debug(f"[QueryInterpretation] Validated filters: {validated_filters}")

        if not validated_filters:
            # No valid filters to apply
            return

        # Build Qdrant filter dict
        filter_dict = self._build_qdrant_filter(validated_filters)
        ctx.logger.debug(f"[QueryInterpretation] Filter dict: {filter_dict}")

        # Write to state (UserFilter will merge with this if it runs)
        state["filter"] = filter_dict

    async def _discover_fields(self, collection_id: str) -> Dict[str, Dict[str, str]]:
        """Discover available fields from collection's entity definitions."""
        from airweave import schemas
        from airweave.platform.locator import resource_locator

        fields = {}

        async with get_db_context() as db:
            # Get source connections for this collection
            source_connections = await crud.source_connection.get_multi_by_collection(
                db, collection_id=collection_id
            )

            if not source_connections:
                raise ValueError(f"No source connections found for collection {collection_id}")

            # Get fields for each source
            for conn in source_connections:
                # Skip PostgreSQL - doesn't support query interpretation
                if conn.short_name == "postgresql":
                    continue

                source = await crud.source.get_by_short_name(db, short_name=conn.short_name)
                if not source:
                    continue

                source_fields = await self._get_source_fields(db, source, resource_locator, schemas)

                if not source_fields:
                    raise ValueError(
                        f"No fields discovered for source '{source.name}'. "
                        f"Cannot perform query interpretation."
                    )

                fields[source.name] = source_fields
                fields[source.short_name] = {}  # Allow both name formats

        if not fields:
            raise ValueError(
                "No valid sources found for query interpretation. "
                "PostgreSQL sources do not support query interpretation."
            )

        return fields

    async def _get_source_fields(
        self, db: Any, source: Any, resource_locator: Any, schemas: Any
    ) -> Dict[str, str]:
        """Get fields for a specific source from its entity definitions."""
        entity_defs = await crud.entity_definition.get_multi_by_source_short_name(
            db, source_short_name=source.short_name
        )

        if not entity_defs:
            return {}

        all_fields = {}

        for entity_def in entity_defs:
            # Convert to schema and get entity class
            entity_schema = schemas.EntityDefinition.model_validate(
                entity_def, from_attributes=True
            )
            entity_class = resource_locator.get_entity_definition(entity_schema)

            # Extract all fields from entity class for filtering
            if hasattr(entity_class, "model_fields"):
                for field_name, field_info in entity_class.model_fields.items():
                    if field_name.startswith("_") or field_name == "airweave_system_metadata":
                        continue

                    # Get description from field
                    description = getattr(field_info, "description", None)

                    # Check json_schema_extra for description (used by AirweaveField)
                    if not description and hasattr(field_info, "json_schema_extra"):
                        extra = field_info.json_schema_extra
                        if isinstance(extra, dict):
                            description = extra.get("description")

                    all_fields[field_name] = description or f"{field_name} field"

        # Add system metadata fields from class constant
        all_fields.update(self.NESTED_SYSTEM_FIELDS)

        return all_fields

    def _build_system_prompt(self, available_fields: Dict[str, Dict[str, str]]) -> str:
        """Build system prompt with available fields."""
        # Format available fields
        fields_description = self._format_available_fields(available_fields)

        # Inject into template
        return QUERY_INTERPRETATION_SYSTEM_PROMPT.format(available_fields=fields_description)

    def _format_available_fields(self, available_fields: Dict[str, Dict[str, str]]) -> str:
        """Format available fields for prompt."""
        lines = []

        # List sources
        sources = list(available_fields.keys())
        lines.append(f"Sources in this collection: {sources}\n")

        # Source-specific fields
        for source, fields in available_fields.items():
            if fields:
                lines.append(f"{source} fields:")
                for fname, desc in sorted(fields.items()):
                    lines.append(f"  - {fname}: {desc}")
                lines.append("")

        return "\n".join(lines)

    def _build_user_prompt(self, query: str, expanded_queries: List[str]) -> str:
        """Build user prompt with query and expansions."""
        all_queries = [query]

        # Add expanded queries if available
        for variant in expanded_queries:
            if variant not in all_queries:
                all_queries.append(variant)

        query_lines = "\n- ".join(all_queries)

        return (
            f"Extract filters from the following search phrasings "
            f"(use ALL to infer constraints).\n"
            f"Consider role/company/location/education/time/source constraints when explicit.\n"
            f"Phrasings (original first):\n"
            f"- {query_lines}"
        )

    def _validate_prompt_length(self, system_prompt: str, user_prompt: str) -> None:
        """Validate prompts fit in context window."""
        # Get LLM tokenizer from provider
        tokenizer = getattr(self.provider, "llm_tokenizer", None)
        if not tokenizer:
            provider_name = self.provider.__class__.__name__
            raise RuntimeError(
                f"Provider {provider_name} does not have an LLM tokenizer. "
                "Cannot validate prompt length."
            )

        system_tokens = self.provider.count_tokens(system_prompt, tokenizer)
        user_tokens = self.provider.count_tokens(user_prompt, tokenizer)

        total_tokens = system_tokens + user_tokens

        if total_tokens > self.provider.model_spec.llm_model.context_window:
            raise ValueError(
                f"Query interpretation prompts too long: {total_tokens} tokens "
                f"exceeds context window of {self.provider.model_spec.llm_model.context_window}"
            )

    def _validate_filters(
        self, filters: List[FilterCondition], available_fields: Dict[str, Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """Validate filter conditions against available fields."""
        allowed_keys = set()
        for source_fields in available_fields.values():
            allowed_keys.update(source_fields.keys())

        validated = []
        for condition in filters:
            # Drop filters for fields that don't exist
            if condition.key not in allowed_keys:
                continue

            # Convert FilterCondition to dict with mapped Qdrant path
            cond_dict = {"key": self._map_to_qdrant_path(condition.key)}

            if condition.match:
                cond_dict["match"] = condition.match

            if condition.range:
                cond_dict["range"] = condition.range

            validated.append(cond_dict)

        return validated

    def _map_to_qdrant_path(self, key: str) -> str:
        """Map field names to Qdrant payload paths."""
        # Already has prefix
        if key.startswith("airweave_system_metadata."):
            return key

        # Needs prefix (from class constant to avoid drift)
        if key in self.NESTED_SYSTEM_FIELDS:
            return f"airweave_system_metadata.{key}"

        # Regular field, no mapping needed
        return key

    def _build_qdrant_filter(self, conditions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build Qdrant filter dict from conditions."""
        if not conditions:
            return {}

        return {"must": conditions}
