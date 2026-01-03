"""Handlers module for sync pipeline.

Contains handlers that execute resolved actions.

Handler Types:
- VectorDBHandler: For destinations requiring client-side chunking/embedding (Qdrant, Pinecone)
- SelfProcessingHandler: For destinations that handle chunking/embedding internally (Vespa)
- RawDataHandler: For raw data storage (ARF)
- PostgresMetadataHandler: For metadata persistence (runs last)

The ActionDispatcher runs destination handlers concurrently, then PostgresMetadataHandler
sequentially to ensure consistency.
"""

from .base import ActionHandler
from .postgres import PostgresMetadataHandler
from .raw_data import RawDataHandler
from .self_processing import SelfProcessingHandler
from .vector_db import VectorDBHandler

__all__ = [
    "ActionHandler",
    "PostgresMetadataHandler",
    "RawDataHandler",
    "SelfProcessingHandler",
    "VectorDBHandler",
]
