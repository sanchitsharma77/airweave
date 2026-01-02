"""Base destination classes."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, ClassVar, Dict, List, Optional
from uuid import UUID

from airweave.core.logging import ContextualLogger
from airweave.core.logging import logger as default_logger
from airweave.platform.entities._base import BaseEntity
from airweave.schemas.search import AirweaveTemporalConfig, SearchResult


class ProcessingRequirement(Enum):
    """What processing a destination expects from Airweave.

    This enum determines how the sync pipeline processes entities before
    sending them to the destination.

    Values:
        CHUNKS_AND_EMBEDDINGS: Destination expects pre-chunked, pre-embedded entities.
            Airweave performs: text extraction → chunking → embedding
            Used by: Qdrant, Pinecone, and other vector databases

        RAW_ENTITIES: Destination handles its own chunking and embedding.
            Airweave sends raw entities without chunking/embedding.
            Used by: Vespa (handles NLP processing internally)
    """

    CHUNKS_AND_EMBEDDINGS = "chunks_embeddings"
    RAW_ENTITIES = "raw"


class BaseDestination(ABC):
    """Common base destination class. This is the umbrella interface for all destinations."""

    # Class variables for integration metadata
    _labels: ClassVar[List[str]] = []

    def __init__(self):
        """Initialize the base destination."""
        self._logger: Optional[ContextualLogger] = (
            None  # Store contextual logger as instance variable
        )

    @property
    def logger(self):
        """Get the logger for this destination, falling back to default if not set."""
        if self._logger is not None:
            return self._logger
        # Return a real default logger
        return default_logger

    def set_logger(self, logger: ContextualLogger) -> None:
        """Set a contextual logger for this destination."""
        self._logger = logger

    @classmethod
    @abstractmethod
    async def create(
        cls,
        credentials: Optional[any],
        config: Optional[dict],
        collection_id: UUID,
        organization_id: Optional[UUID] = None,
        logger: Optional[ContextualLogger] = None,
    ) -> "BaseDestination":
        """Create a new destination with credentials and config (matches source pattern).

        Args:
            credentials: Authentication credentials (e.g., S3AuthConfig, QdrantAuthConfig)
            config: Configuration parameters (e.g., bucket_name, url)
            collection_id: Collection UUID
            organization_id: Organization UUID
            logger: Logger instance
        """
        pass

    @abstractmethod
    async def setup_collection(self, collection_id: UUID, vector_size: int) -> None:
        """Set up the collection for storing entities."""
        pass

    @abstractmethod
    async def insert(self, entity: BaseEntity) -> None:
        """Insert a single entity into the destination."""
        pass

    @abstractmethod
    async def bulk_insert(self, entities: list[BaseEntity]) -> None:
        """Bulk insert entities into the destination."""
        pass

    @abstractmethod
    async def delete(self, db_entity_id: UUID) -> None:
        """Delete a single entity from the destination."""
        pass

    @abstractmethod
    async def bulk_delete(self, entity_ids: list[str], sync_id: UUID) -> None:
        """Bulk delete entities from the destination within a given sync."""
        pass

    @abstractmethod
    async def delete_by_sync_id(self, sync_id: UUID) -> None:
        """Delete entities from the destination by sync ID."""
        pass

    @abstractmethod
    async def bulk_delete_by_parent_id(self, parent_id: str, sync_id: UUID) -> None:
        """Bulk delete entities from the destination by parent ID within a given sync."""
        pass

    async def bulk_delete_by_parent_ids(self, parent_ids: list[str], sync_id: UUID) -> None:
        """Bulk delete entities for multiple parent IDs within a given sync.

        Default fan-out implementation that calls `bulk_delete_by_parent_id` for each ID.
        Destinations can override this to issue a single optimized call.
        """
        for pid in parent_ids:
            await self.bulk_delete_by_parent_id(pid, sync_id)

    @abstractmethod
    async def search(
        self,
        queries: List[str],
        airweave_collection_id: UUID,
        limit: int,
        offset: int,
        filter: Optional[Dict[str, Any]] = None,
        dense_embeddings: Optional[List[List[float]]] = None,
        sparse_embeddings: Optional[List[Any]] = None,
        retrieval_strategy: str = "hybrid",
        temporal_config: Optional[AirweaveTemporalConfig] = None,
    ) -> List[SearchResult]:
        """Execute search against the destination.

        This is the standard search interface that all destinations must implement.
        Destinations handle embedding generation (if needed) and filter translation internally.

        Args:
            queries: List of search query texts (supports query expansion)
            airweave_collection_id: Airweave collection UUID for multi-tenant filtering
            limit: Maximum number of results to return
            offset: Number of results to skip (pagination)
            filter: Optional filter dict (Airweave canonical format, destination translates)
            dense_embeddings: Pre-computed dense embeddings (if client-side embedding)
            sparse_embeddings: Pre-computed sparse embeddings for hybrid search
            retrieval_strategy: Search strategy - "hybrid", "neural", or "keyword"
            temporal_config: Optional temporal relevance config (destination translates)

        Returns:
            List of SearchResult objects in the standard format
        """
        pass

    def translate_filter(self, filter: Optional[Dict[str, Any]]) -> Any:
        """Translate Airweave filter to destination-native format.

        Default implementation is passthrough.
        Override this method for destinations that use different filter formats.

        Args:
            filter: Airweave canonical filter dict

        Returns:
            Destination-native filter format
        """
        return filter

    def translate_temporal(self, config: Optional[AirweaveTemporalConfig]) -> Any:
        """Translate Airweave temporal config to destination-native format.

        Default implementation is passthrough. Override for destinations that
        require different temporal relevance configurations.

        Args:
            config: Airweave temporal relevance configuration

        Returns:
            Destination-native temporal config (or None if not supported)
        """
        return config

    @abstractmethod
    async def has_keyword_index(self) -> bool:
        """Check if the destination has a keyword index."""
        pass

    @property
    def processing_requirement(self) -> ProcessingRequirement:
        """What processing this destination requires from Airweave.

        Override in subclasses to change behavior. Default is CHUNKS_AND_EMBEDDINGS
        for backward compatibility with existing vector DBs.

        Returns:
            ProcessingRequirement indicating what processing Airweave should perform
        """
        return ProcessingRequirement.CHUNKS_AND_EMBEDDINGS

    async def bulk_insert_raw(self, entities: list[BaseEntity]) -> None:
        """Bulk insert raw (non-chunked, non-embedded) entities.

        Used by destinations with processing_requirement=RAW_ENTITIES.
        Default implementation raises NotImplementedError.

        Args:
            entities: Raw entities without chunking/embedding

        Raises:
            NotImplementedError: If destination doesn't support raw inserts
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support raw entity inserts. "
            "Override bulk_insert_raw() or set processing_requirement to CHUNKS_AND_EMBEDDINGS."
        )


class VectorDBDestination(BaseDestination):
    """Abstract base class for destinations backed by a vector database.

    Inherits from BaseDestination and can have additional vector-specific methods if necessary.
    """

    @abstractmethod
    async def get_vector_config_names(self) -> list[str]:
        """Get the vector config names for the destination."""
        pass
