"""Destinations module.

Contains destination adapters and base classes for syncing data to various stores.

Key Classes:
- BaseDestination: Abstract base class for all destinations
- VectorDBDestination: Base class for vector database destinations
- ProcessingRequirement: Enum indicating what processing a destination expects

Processing Requirements:
- CHUNKS_AND_EMBEDDINGS: Destination expects pre-chunked, pre-embedded entities
- RAW_ENTITIES: Destination handles its own chunking and embedding
"""

from ._base import BaseDestination, ProcessingRequirement, VectorDBDestination

__all__ = [
    "BaseDestination",
    "ProcessingRequirement",
    "VectorDBDestination",
]
