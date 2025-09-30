"""Collections search endpoints.

These endpoints are mounted under the `/collections` prefix in `api/v1/api.py`,
so paths remain `/collections/{readable_id}/search` et al., while being defined
in this dedicated module.
"""

import asyncio
import json
from typing import Any, Dict

from fastapi import Depends, Path
from fastapi.responses import StreamingResponse
from qdrant_client.http.models import Filter as QdrantFilter
from sqlalchemy.ext.asyncio import AsyncSession

from airweave import schemas
from airweave.analytics import track_search_operation
from airweave.api import deps
from airweave.api.context import ApiContext
from airweave.api.router import TrailingSlashRouter
from airweave.core.guard_rail_service import GuardRailService
from airweave.core.pubsub import core_pubsub
from airweave.core.shared_models import ActionType
from airweave.db.session import AsyncSessionLocal
from airweave.schemas.search import SearchRequest
from airweave.search.service import service

router = TrailingSlashRouter()


@router.post(
    "/{readable_id}/search",
    response_model=schemas.SearchResponse,
)
@track_search_operation()
async def search(
    readable_id: str = Path(
        ...,
        description="The unique readable identifier of the collection",
    ),
    search_request: SearchRequest = ...,
    db: AsyncSession = Depends(deps.get_db),
    ctx: ApiContext = Depends(deps.get_context),
    guard_rail: GuardRailService = Depends(deps.get_guard_rail_service),
) -> schemas.SearchResponse:
    """Search your collection."""
    await guard_rail.is_allowed(ActionType.QUERIES)

    ctx.logger.info(f"Starting search for collection '{readable_id}'")
    response = await service.search(
        request_id=ctx.request_id,
        readable_collection_id=readable_id,
        search_request=search_request,
        stream=False,
        db=db,
        ctx=ctx,
    )
    ctx.logger.info(f"Search completed for collection '{readable_id}'")

    await guard_rail.increment(ActionType.QUERIES)

    return response


@router.post("/{readable_id}/search/stream")
async def stream_search_collection_advanced(  # noqa: C901 - streaming orchestration is acceptable
    readable_id: str = Path(
        ..., description="The unique readable identifier of the collection to search"
    ),
    search_request: SearchRequest = ...,
    db: AsyncSession = Depends(deps.get_db),
    ctx: ApiContext = Depends(deps.get_context),
    guard_rail: GuardRailService = Depends(deps.get_guard_rail_service),
) -> StreamingResponse:
    """Server-Sent Events (SSE) streaming endpoint for advanced search.

    Initializes a streaming session and relays events from Redis Pub/Sub.
    """
    request_id = ctx.request_id
    ctx.logger.info(
        f"[SearchStream] Starting stream for collection '{readable_id}' id={request_id}"
    )

    await guard_rail.is_allowed(ActionType.QUERIES)

    from airweave.analytics.search_analytics import build_search_properties, track_search_event

    if ctx and search_request.query:
        properties = build_search_properties(
            ctx=ctx,
            query=search_request.query,
            collection_slug=readable_id,
            duration_ms=0,
            search_type="streaming",
        )
        track_search_event(ctx, properties, "search_stream_start")

    pubsub = await core_pubsub.subscribe("search", request_id)

    async def _run_search() -> None:
        try:
            async with AsyncSessionLocal() as search_db:
                await service.search(
                    request_id=request_id,
                    readable_id=readable_id,
                    search_request=search_request,
                    stream=True,
                    db=search_db,
                    ctx=ctx,
                )
        except Exception as e:  # noqa: BLE001 - report to stream
            await core_pubsub.publish(
                "search",
                request_id,
                {"type": "error", "message": str(e)},
            )

    search_task = asyncio.create_task(_run_search())

    async def event_stream():  # noqa: C901 - complex loop acceptable
        try:
            import datetime as _dt

            connected_event = {
                "type": "connected",
                "request_id": request_id,
                "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            }
            yield f"data: {json.dumps(connected_event)}\n\n"

            last_heartbeat = asyncio.get_event_loop().time()
            heartbeat_interval = 30

            async for message in pubsub.listen():
                now = asyncio.get_event_loop().time()
                if now - last_heartbeat > heartbeat_interval:
                    heartbeat_event = {
                        "type": "heartbeat",
                        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                    }
                    yield f"data: {json.dumps(heartbeat_event)}\n\n"
                    last_heartbeat = now

                if message["type"] == "message":
                    data = message["data"]
                    yield f"data: {data}\n\n"

                    try:
                        parsed = json.loads(data)
                        if isinstance(parsed, dict) and parsed.get("type") == "done":
                            ctx.logger.info(
                                f"[SearchStream] Done event received for search:{request_id}. "
                                "Closing stream"
                            )
                            try:
                                await guard_rail.increment(ActionType.QUERIES)
                            except Exception:
                                pass
                            break
                    except Exception:
                        pass

                elif message["type"] == "subscribe":
                    ctx.logger.info(f"[SearchStream] Subscribed to channel search:{request_id}")
                else:
                    current = asyncio.get_event_loop().time()
                    if current - last_heartbeat > heartbeat_interval:
                        heartbeat_event = {
                            "type": "heartbeat",
                            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                        }
                        yield f"data: {json.dumps(heartbeat_event)}\n\n"
                        last_heartbeat = current

        except asyncio.CancelledError:
            ctx.logger.info(f"[SearchStream] Cancelled stream id={request_id}")
        except Exception as e:  # noqa: BLE001 - emit error event
            ctx.logger.error(f"[SearchStream] Error id={request_id}: {str(e)}")
            import datetime as _dt

            error_event = {
                "type": "error",
                "message": str(e),
                "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            }
            yield f"data: {json.dumps(error_event)}\n\n"
        finally:
            if not search_task.done():
                search_task.cancel()
                try:
                    await search_task
                except Exception:
                    pass
            try:
                await pubsub.close()
                ctx.logger.info(
                    f"[SearchStream] Closed pubsub subscription for search:{request_id}"
                )
            except Exception:
                pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Type": "text/event-stream",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/internal/filter-schema")
async def get_filter_schema() -> Dict[str, Any]:
    """Get the JSON schema for Qdrant filter validation.

    This endpoint returns the JSON schema that can be used to validate
    filter objects in the frontend.
    """
    schema = QdrantFilter.model_json_schema()

    if "$defs" in schema:
        for _def_name, def_schema in schema.get("$defs", {}).items():
            if "discriminator" in def_schema:
                del def_schema["discriminator"]

    return schema
