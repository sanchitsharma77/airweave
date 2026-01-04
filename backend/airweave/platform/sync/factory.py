"""Module for sync factory that creates context and orchestrator instances.

This factory uses focused builders to construct sync components:
- InfraBuilder: Logger and infrastructure
- SourceBuilder: Source with credentials, OAuth, proxy
- DestinationBuilder: Destinations with credentials
- TrackingBuilder: Entity tracker and publisher

The factory composes these builders to create SyncOrchestrator instances.
"""

import asyncio
import time
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from airweave import schemas
from airweave.api.context import ApiContext
from airweave.core.config import settings
from airweave.core.logging import logger
from airweave.platform.sync.actions import ActionDispatcher, ActionResolver
from airweave.platform.sync.builders import (
    DestinationBuilder,
    InfraBuilder,
    SourceBuilder,
    TrackingBuilder,
)
from airweave.platform.sync.bundles import BatchConfig, SyncIdentity
from airweave.platform.sync.config import SyncExecutionConfig
from airweave.platform.sync.context import SyncContext
from airweave.platform.sync.entity_pipeline import EntityPipeline
from airweave.platform.sync.handlers import (
    ArfHandler,
    DestinationHandler,
    PostgresMetadataHandler,
)
from airweave.platform.sync.orchestrator import SyncOrchestrator
from airweave.platform.sync.stream import AsyncSourceStream
from airweave.platform.sync.worker_pool import AsyncWorkerPool


class SyncFactory:
    """Factory for sync orchestrator.

    Uses focused builders to construct sync components:
    - InfraBuilder: Logger and infrastructure
    - SourceBuilder: Source with credentials, OAuth, proxy
    - DestinationBuilder: Destinations with credentials
    - TrackingBuilder: Entity tracker and publisher
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
        logger.info("Creating sync context via builders...")

        # Create sync context using builders
        sync_context = await cls._create_sync_context(
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

        # Create pipeline components
        logger.debug("Initializing pipeline components...")

        # 1. Action Resolver
        action_resolver = ActionResolver(entity_map=sync_context.entity_map)

        # 2. Handlers - conditionally created based on execution_config
        handlers = cls._create_handlers(sync_context, execution_config)

        # 3. Action Dispatcher
        action_dispatcher = ActionDispatcher(handlers=handlers)

        # 4. Entity Pipeline
        entity_pipeline = EntityPipeline(
            entity_tracker=sync_context.entity_tracker,
            action_resolver=action_resolver,
            action_dispatcher=action_dispatcher,
        )

        # Create worker pool
        worker_pool = AsyncWorkerPool(max_workers=max_workers, logger=sync_context.logger)

        # Create stream
        stream = AsyncSourceStream(
            source_generator=sync_context.source_instance.generate_entities(),
            queue_size=10000,  # TODO: make this configurable
            logger=sync_context.logger,
        )

        # Create dedicated orchestrator instance with all components
        orchestrator = SyncOrchestrator(
            entity_pipeline=entity_pipeline,
            worker_pool=worker_pool,
            stream=stream,
            sync_context=sync_context,
        )

        logger.info(f"Total orchestrator initialization took {time.time() - init_start:.2f}s")

        return orchestrator

    @classmethod
    async def _create_sync_context(
        cls,
        db: AsyncSession,
        sync: schemas.Sync,
        sync_job: schemas.SyncJob,
        collection: schemas.Collection,
        connection: schemas.Connection,
        ctx: ApiContext,
        access_token: Optional[str] = None,
        force_full_sync: bool = False,
        execution_config: Optional[SyncExecutionConfig] = None,
    ) -> SyncContext:
        """Create a sync context using builders.

        This method coordinates the builders to construct all bundles,
        then assembles them into a SyncContext.

        Args:
            db: Database session
            sync: The sync configuration
            sync_job: The sync job
            collection: The collection to sync to
            connection: The connection
            ctx: The API context
            access_token: Optional token to use instead of stored credentials
            force_full_sync: If True, forces a full sync with orphaned entity deletion
            execution_config: Optional execution config for controlling sync behavior

        Returns:
            SyncContext object with all required components
        """
        # Step 1: Get source connection ID early (needed for logger dimensions)
        source_connection_id = await SourceBuilder.get_source_connection_id(db, sync, ctx)

        # Step 2: Build infrastructure (logger) - needed by all other builders
        infra, contextual_logger = InfraBuilder.build(
            sync=sync,
            sync_job=sync_job,
            collection=collection,
            source_connection_id=source_connection_id,
            ctx=ctx,
        )

        contextual_logger.info("Building sync context via focused builders...")

        # Step 3: Build all bundles in parallel (where possible)
        # Source and destination builders are independent, tracking depends on db
        source_task = SourceBuilder.build(
            db=db,
            sync=sync,
            sync_job=sync_job,
            ctx=ctx,
            logger=contextual_logger,
            access_token=access_token,
            force_full_sync=force_full_sync,
            execution_config=execution_config,
        )

        destination_task = DestinationBuilder.build(
            db=db,
            sync=sync,
            collection=collection,
            ctx=ctx,
            logger=contextual_logger,
            execution_config=execution_config,
        )

        tracking_task = TrackingBuilder.build(
            db=db,
            sync=sync,
            sync_job=sync_job,
            ctx=ctx,
            logger=contextual_logger,
        )

        # Run all builders in parallel
        source_bundle, destination_bundle, tracking_bundle = await asyncio.gather(
            source_task,
            destination_task,
            tracking_task,
        )

        # Step 4: Create batch config
        batch_config = BatchConfig(
            should_batch=True,
            batch_size=64,
            max_batch_latency_ms=200,
            force_full_sync=force_full_sync,
        )

        # Step 5: Create identity
        identity = SyncIdentity(
            sync_id=sync.id,
            collection_id=collection.id,
            organization_id=ctx.organization.id,
            sync_job_id=sync_job.id,
        )

        # Step 6: Assemble SyncContext directly from bundles (depth 1)
        sync_context = SyncContext(
            identity=identity,
            infra=infra,
            source=source_bundle,
            destinations=destination_bundle,
            tracking=tracking_bundle,
            batch_config=batch_config,
            sync=sync,
            sync_job=sync_job,
            collection=collection,
            connection=connection,
            execution_config=execution_config,
        )

        contextual_logger.info("Sync context created via builders")

        return sync_context

    @classmethod
    def _create_handlers(
        cls,
        sync_context: SyncContext,
        execution_config: Optional[SyncExecutionConfig],
    ) -> list:
        """Create handlers based on execution config.

        Args:
            sync_context: Sync context with destinations and logger
            execution_config: Optional execution config for filtering

        Returns:
            List of action handlers
        """
        if execution_config:
            enable_vector = execution_config.enable_vector_handlers
            enable_raw = execution_config.enable_raw_data_handler
            enable_postgres = execution_config.enable_postgres_handler
        else:
            enable_vector = True
            enable_raw = True
            enable_postgres = True

        handlers = []
        destinations = sync_context.destination_list

        # Add VectorDBHandler if enabled
        if enable_vector and destinations:
            handler = DestinationHandler(destinations=destinations)
            handlers.append(handler)

            # Log what processing requirements are in use
            processor_info = [
                f"{d.__class__.__name__}→{d.processing_requirement.value}" for d in destinations
            ]
            sync_context.logger.info(
                f"Created DestinationHandler with requirements: {processor_info}"
            )
        elif destinations:
            sync_context.logger.info(
                f"Skipping VectorDBHandler (disabled by execution_config) for "
                f"{len(destinations)} destination(s)"
            )

        # Add ArfHandler if enabled
        if enable_raw:
            handlers.append(ArfHandler())
        else:
            sync_context.logger.info("Skipping ArfHandler (disabled by execution_config)")

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

        return handlers
