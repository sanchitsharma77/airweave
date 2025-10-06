"""Temporal relevance operation.

Computes dynamic time-based decay configuration by analyzing the actual
time range of the (optionally filtered) collection. This enables recency-aware
ranking that respects the dataset's time distribution.
"""

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel
from qdrant_client.http import models as rest

from airweave.api.context import ApiContext
from airweave.platform.destinations.qdrant import QdrantDestination
from airweave.search.context import SearchContext

from ._base import SearchOperation


class DecayConfig(BaseModel):
    """Configuration for time-based decay in Qdrant queries."""

    decay_type: str  # "linear", "exponential", "gaussian"
    datetime_field: str
    target_datetime: datetime
    scale_seconds: float
    midpoint: float
    weight: float

    def get_scale_seconds(self) -> float:
        """Get scale in seconds for decay calculation."""
        return self.scale_seconds


class TemporalRelevance(SearchOperation):
    """Compute dynamic temporal decay configuration for recency-aware search."""

    DATETIME_FIELD = "airweave_system_metadata.airweave_updated_at"
    DECAY_TYPE = "linear"
    MIDPOINT = 0.5

    def __init__(self, weight: float) -> None:
        """Initialize with temporal relevance weight."""
        self.weight = weight

    def depends_on(self) -> List[str]:
        """Depends on filter operations."""
        return ["QueryInterpretation", "UserFilter"]

    async def execute(self, context: SearchContext, state: dict[str, Any], ctx: ApiContext) -> None:
        """Compute decay configuration from collection timestamps."""
        ctx.logger.debug(
            "[TemporalRelevance] Computing decay configuration from collection timestamps"
        )

        # Get filter from state if available (respects filtered timespan)
        filter_dict = state.get("filter")
        qdrant_filter = self._convert_to_qdrant_filter(filter_dict)

        # Connect to Qdrant
        destination = await QdrantDestination.create(
            collection_id=context.collection_id, logger=None
        )

        # Get oldest and newest timestamps
        oldest, newest = await self._get_min_max_timestamps(
            destination, str(context.collection_id), qdrant_filter
        )
        ctx.logger.debug(f"[TemporalRelevance] Oldest timestamp: {oldest}")
        ctx.logger.debug(f"[TemporalRelevance] Newest timestamp: {newest}")

        if not oldest or not newest:
            raise ValueError(
                "Could not determine time range for temporal relevance. "
                "Collection might be empty or have no valid timestamps."
            )

        if newest <= oldest:
            raise ValueError(
                f"Invalid time range: newest ({newest}) <= oldest ({oldest}). "
                "Cannot compute temporal decay."
            )

        # Calculate scale as full time span for linear decay
        scale_seconds = (newest - oldest).total_seconds()

        if scale_seconds <= 0:
            raise ValueError(f"Time span is zero or negative: {scale_seconds} seconds")

        # Build decay config
        decay_config = DecayConfig(
            decay_type=self.DECAY_TYPE,
            datetime_field=self.DATETIME_FIELD,
            target_datetime=newest,  # Use newest item time, not current time
            scale_seconds=scale_seconds,
            midpoint=self.MIDPOINT,
            weight=self.weight,
        )
        ctx.logger.debug(f"[TemporalRelevance] Decay config: {decay_config}")

        # Write to state
        state["decay_config"] = decay_config

    def _convert_to_qdrant_filter(self, filter_dict: Optional[dict]) -> Optional[rest.Filter]:
        """Convert filter dict to Qdrant Filter object."""
        if not filter_dict:
            return None

        try:
            return rest.Filter.model_validate(filter_dict)
        except Exception as e:
            raise ValueError(f"Invalid filter format for Qdrant: {e}") from e

    async def _get_min_max_timestamps(
        self,
        destination: QdrantDestination,
        collection_id: str,
        qdrant_filter: Optional[rest.Filter],
    ) -> tuple[Optional[datetime], Optional[datetime]]:
        """Fetch oldest and newest timestamps using ordered scrolls."""
        # Get oldest
        oldest_points = await destination.client.scroll(
            collection_name=collection_id,
            limit=1,
            with_payload=[self.DATETIME_FIELD],
            order_by=rest.OrderBy(key=self.DATETIME_FIELD, direction="asc"),
            scroll_filter=qdrant_filter,
        )

        # Get newest
        newest_points = await destination.client.scroll(
            collection_name=collection_id,
            limit=1,
            with_payload=[self.DATETIME_FIELD],
            order_by=rest.OrderBy(key=self.DATETIME_FIELD, direction="desc"),
            scroll_filter=qdrant_filter,
        )

        oldest = self._extract_datetime(oldest_points)
        newest = self._extract_datetime(newest_points)

        return oldest, newest

    def _extract_datetime(self, scroll_result: tuple) -> Optional[datetime]:
        """Extract datetime from Qdrant scroll result."""
        if not scroll_result or not scroll_result[0]:
            return None

        point = scroll_result[0][0]
        if not point or not hasattr(point, "payload"):
            return None

        # Navigate nested path: airweave_system_metadata.airweave_updated_at
        payload = point.payload
        parts = self.DATETIME_FIELD.split(".")

        value = payload
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None

        # Parse datetime
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        elif isinstance(value, datetime):
            return value

        return None
