"""Focused builders for sync component construction.

Each builder handles a single concern:
- InfraBuilder: Logger and infrastructure setup
- SourceBuilder: Source creation with credentials, OAuth, proxy
- DestinationBuilder: Destination creation with credentials
- TrackingBuilder: Entity tracker and publisher setup

Usage:
    # Builders can run in parallel since they're independent
    source_bundle, dest_bundle, tracking_bundle = await asyncio.gather(
        SourceBuilder.build(...),
        DestinationBuilder.build(...),
        TrackingBuilder.build(...),
    )
"""

from airweave.platform.sync.builders.destination import DestinationBuilder
from airweave.platform.sync.builders.infra import InfraBuilder
from airweave.platform.sync.builders.source import SourceBuilder
from airweave.platform.sync.builders.tracking import TrackingBuilder

__all__ = [
    "InfraBuilder",
    "SourceBuilder",
    "DestinationBuilder",
    "TrackingBuilder",
]

