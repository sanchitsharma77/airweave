"""API routes for the FastAPI application."""

from airweave.api.router import TrailingSlashRouter
from airweave.api.v1.endpoints import (
    admin,
    api_keys,
    auth_providers,
    billing,
    collections,
    connections,
    cursor_dev,
    dag,
    destinations,
    embedding_models,
    entities,
    entity_counts,
    file_retrieval,
    health,
    organizations,
    search,
    source_connections,
    sources,
    sync,
    transformers,
    usage,
    users,
)
from airweave.core.config import settings

# Use our custom router that handles trailing slashes
api_router = TrailingSlashRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(api_keys.router, prefix="/api-keys", tags=["api-keys"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
api_router.include_router(billing.router, prefix="/billing", tags=["billing"])
api_router.include_router(usage.router, prefix="/usage", tags=["usage"])
api_router.include_router(sources.router, prefix="/sources", tags=["sources"])
api_router.include_router(destinations.router, prefix="/destinations", tags=["destinations"])
api_router.include_router(
    embedding_models.router, prefix="/embedding_models", tags=["embedding_models"]
)
api_router.include_router(auth_providers.router, prefix="/auth-providers", tags=["auth-providers"])
api_router.include_router(collections.router, prefix="/collections", tags=["collections"])
api_router.include_router(search.router, prefix="/collections", tags=["collections"])
api_router.include_router(connections.router, prefix="/connections", tags=["connections"])
api_router.include_router(
    source_connections.router, prefix="/source-connections", tags=["source-connections"]
)
api_router.include_router(sync.router, prefix="/sync", tags=["sync"])
api_router.include_router(dag.router, prefix="/dag", tags=["dag"])
api_router.include_router(entities.router, prefix="/entities", tags=["entities"])
api_router.include_router(entity_counts.router, prefix="/entity-counts", tags=["entity-counts"])
api_router.include_router(transformers.router, prefix="/transformers", tags=["transformers"])
api_router.include_router(file_retrieval.router, prefix="/files", tags=["files"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])

# Only include cursor development endpoints if LOCAL_CURSOR_DEVELOPMENT is enabled
if settings.LOCAL_CURSOR_DEVELOPMENT:
    api_router.include_router(cursor_dev.router, prefix="/cursor-dev", tags=["Cursor Development"])
