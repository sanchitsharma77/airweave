"""Context builders for platform operations.

Builders are factory classes that construct context objects.
Each builder creates a single context type.

Builder Types:
- ScopeContextBuilder: Creates ScopeContext
- InfraContextBuilder: Creates InfraContext
- SourceContextBuilder: Creates SourceContext
- DestinationsContextBuilder: Creates DestinationsContext
- TrackingContextBuilder: Creates TrackingContext
- SyncContextBuilder: Orchestrates all builders to create SyncContext
- CleanupContextBuilder: Creates CleanupContext for deletion operations

Note: Dispatcher builders live in platform/sync/actions/{domain}/
"""

from airweave.platform.builders.cleanup import CleanupContextBuilder
from airweave.platform.builders.destinations import DestinationsContextBuilder
from airweave.platform.builders.infra import InfraContextBuilder
from airweave.platform.builders.scope import ScopeContextBuilder
from airweave.platform.builders.source import SourceContextBuilder
from airweave.platform.builders.sync import SyncContextBuilder
from airweave.platform.builders.tracking import TrackingContextBuilder

__all__ = [
    "CleanupContextBuilder",
    "DestinationsContextBuilder",
    "InfraContextBuilder",
    "ScopeContextBuilder",
    "SourceContextBuilder",
    "SyncContextBuilder",
    "TrackingContextBuilder",
]
