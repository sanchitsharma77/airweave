"""Module for sync factory that creates orchestrator instances.

This factory uses SyncContextBuilder to construct the sync context,
then creates the remaining pipeline components.
"""

import time
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from airweave import schemas
from airweave.api.context import ApiContext
from airweave.core.config import settings
from airweave.core.logging import logger
from airweave.platform.builders import SyncContextBuilder
from airweave.platform.destinations._base import BaseDestination, ProcessingRequirement
from airweave.platform.sync.actions import ActionDispatcher, ActionResolver
from airweave.platform.sync.config import SyncExecutionConfig
from airweave.platform.sync.context import SyncContext
from airweave.platform.sync.entity_pipeline import EntityPipeline
from airweave.platform.sync.handlers import (
    PostgresMetadataHandler,
    RawDataHandler,
    VectorDBHandler,
)
from airweave.platform.sync.orchestrator import SyncOrchestrator
from airweave.platform.sync.stream import AsyncSourceStream
from airweave.platform.sync.worker_pool import AsyncWorkerPool


class SyncFactory:
    """Factory for sync orchestrator.

    Uses SyncContextBuilder to create contexts, then builds the
    action resolver and dispatcher with handlers.
    """

    @classmethod
    async def create_orchestrator(
        cls,
        db: AsyncSession,
        sync: schemas.Sync,
        sync_job: schemas.SyncJob,
        collection: schemas.Collection,
        connection: schemas.Connection,
        ctx: ApiContext,
        access_token: Optional[str] = None,
        max_workers: int = None,
        force_full_sync: bool = False,
        execution_config: Optional[SyncExecutionConfig] = None,
    ) -> SyncOrchestrator:
        """Create a dedicated orchestrator instance for a sync run.

        This method creates all necessary components for a sync run, including the
        context and a dedicated orchestrator instance for concurrent execution.

        Args:
            db: Database session
            sync: The sync configuration
            sync_job: The sync job
            collection: The collection to sync to
            connection: The connection
            ctx: The API context
            access_token: Optional token to use instead of stored credentials
            max_workers: Maximum number of concurrent workers (default: from settings)
            force_full_sync: If True, forces a full sync with orphaned entity deletion
            execution_config: Optional execution config for controlling sync behavior

        Returns:
            A dedicated SyncOrchestrator instance
        """
        # Use configured value if max_workers not specified
        if max_workers is None:
            max_workers = settings.SYNC_MAX_WORKERS
            logger.debug(f"Using configured max_workers: {max_workers}")

        # Track initialization timing
        init_start = time.time()
        logger.info("Creating sync context via context builders...")

        # Step 1: Build sync context using SyncContextBuilder
        sync_context = await SyncContextBuilder.build(
            db=db,
            sync=sync,
            sync_job=sync_job,
            collection=collection,
            connection=connection,
            ctx=ctx,
            access_token=access_token,
            force_full_sync=force_full_sync,
            execution_config=execution_config,
        )

        logger.debug(f"Sync context created in {time.time() - init_start:.2f}s")

        # Step 2: Create pipeline components
        logger.debug("Initializing pipeline components...")

        # Action Resolver
        action_resolver = ActionResolver(entity_map=sync_context.entity_map)

        # Handlers - conditionally created based on execution_config
        config = sync_context.execution_config
        enable_vector = config is None or config.enable_vector_handlers
        enable_raw = config is None or config.enable_raw_data_handler
        enable_postgres = config is None or config.enable_postgres_handler

        handlers = []

        # Add VectorDBHandler if enabled
        if enable_vector:
            vector_handlers = cls._create_destination_handlers(sync_context)
            handlers.extend(vector_handlers)
        elif sync_context.destinations:
            sync_context.logger.info(
                f"Skipping VectorDBHandler (disabled by execution_config) for "
                f"{len(sync_context.destinations)} destination(s)"
            )

        # Add RawDataHandler if enabled
        if enable_raw:
            handlers.append(RawDataHandler())
        else:
            sync_context.logger.info("Skipping RawDataHandler (disabled by execution_config)")

        # Add PostgresMetadataHandler if enabled (always runs last)
        if enable_postgres:
            handlers.append(PostgresMetadataHandler())
        else:
            sync_context.logger.info(
                "Skipping PostgresMetadataHandler (disabled by execution_config)"
            )

        if not handlers:
            sync_context.logger.warning(
                "No handlers created - sync will fetch entities but not persist them"
            )

        # Action Dispatcher
        action_dispatcher = ActionDispatcher(handlers=handlers)

        # Entity Pipeline
        entity_pipeline = EntityPipeline(
            entity_tracker=sync_context.entity_tracker,
            action_resolver=action_resolver,
            action_dispatcher=action_dispatcher,
        )

        # Step 3: Create worker pool
        worker_pool = AsyncWorkerPool(max_workers=max_workers, logger=sync_context.logger)

        # Step 4: Create stream
        stream = AsyncSourceStream(
            source_generator=sync_context.source.generate_entities(),
            queue_size=10000,  # TODO: make this configurable
            logger=sync_context.logger,
        )

        # Step 5: Create orchestrator
        orchestrator = SyncOrchestrator(
            entity_pipeline=entity_pipeline,
            worker_pool=worker_pool,
            stream=stream,
            sync_context=sync_context,
        )

        logger.info(f"Total orchestrator initialization took {time.time() - init_start:.2f}s")

        return orchestrator

    @classmethod
    def _create_destination_handlers(
        cls,
        sync_context: SyncContext,
    ) -> list:
        """Create destination handlers grouped by processing requirements.

        This method groups destinations by their processing requirements and creates
        appropriate handlers:
        - VectorDBHandler: For destinations needing chunking/embedding (Qdrant, Pinecone)

        Args:
            sync_context: Sync context with destinations and logger

        Returns:
            List of destination handlers (may be empty if no destinations)
        """
        from airweave.platform.sync.handlers.base import ActionHandler

        handlers: list[ActionHandler] = []

        # Group destinations by processing requirement
        vector_db_destinations: list[BaseDestination] = []
        self_processing_destinations: list[BaseDestination] = []

        for dest in sync_context.destinations:
            requirement = dest.processing_requirement
            if requirement == ProcessingRequirement.CHUNKS_AND_EMBEDDINGS:
                vector_db_destinations.append(dest)
            elif requirement == ProcessingRequirement.RAW_ENTITIES:
                self_processing_destinations.append(dest)
            else:
                # Default to vector DB for unknown requirements (backward compat)
                sync_context.logger.warning(
                    f"Unknown processing requirement {requirement} for {dest.__class__.__name__}, "
                    "defaulting to CHUNKS_AND_EMBEDDINGS"
                )
                vector_db_destinations.append(dest)

        # Create handlers for each non-empty group
        if vector_db_destinations:
            vector_handler = VectorDBHandler(destinations=vector_db_destinations)
            handlers.append(vector_handler)
            sync_context.logger.info(
                f"Created VectorDBHandler for {len(vector_db_destinations)} destination(s): "
                f"{[d.__class__.__name__ for d in vector_db_destinations]}"
            )

        if not handlers:
            sync_context.logger.warning(
                "No destination handlers created - sync has no valid destinations"
            )

        return handlers
