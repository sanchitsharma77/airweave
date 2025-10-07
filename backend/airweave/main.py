"""Main module of the FastAPI application.

This module sets up the FastAPI application and the middleware to log incoming requests
and unhandled exceptions.
"""

import os
import subprocess
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from airweave.api.middleware import (
    DynamicCORSMiddleware,
    add_request_id,
    airweave_exception_handler,
    exception_logging_middleware,
    invalid_state_exception_handler,
    log_requests,
    not_found_exception_handler,
    payment_required_exception_handler,
    permission_exception_handler,
    usage_limit_exceeded_exception_handler,
    validation_exception_handler,
)
from airweave.api.router import TrailingSlashRouter
from airweave.api.v1.api import api_router
from airweave.core.config import settings
from airweave.core.exceptions import (
    AirweaveException,
    InvalidStateError,
    NotFoundException,
    PaymentRequiredException,
    PermissionException,
    UsageLimitExceededException,
)
from airweave.core.logging import logger
from airweave.db.init_db import init_db
from airweave.db.session import AsyncSessionLocal
from airweave.platform.db_sync import sync_platform_components
from airweave.platform.entities._base import ensure_file_entity_models


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events.

    Runs alembic migrations and syncs platform components.
    """
    async with AsyncSessionLocal() as db:
        if settings.RUN_ALEMBIC_MIGRATIONS:
            logger.info("Running alembic migrations...")
            env = os.environ.copy()
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            env["PYTHONPATH"] = backend_dir
            subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "heads"],
                check=True,
                cwd=backend_dir,
                env=env,
            )
        if settings.RUN_DB_SYNC:
            # Ensure all FileEntity subclasses have their parent and chunk models created
            ensure_file_entity_models()
            await sync_platform_components("airweave/platform", db)
        await init_db(db)

    yield


# Create FastAPI app with our custom router and disable FastAPI's built-in redirects
app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url="/openapi.json",
    lifespan=lifespan,
    router=TrailingSlashRouter(),
    redirect_slashes=False,  # Critical: disable FastAPI's built-in slash redirects
)

app.include_router(api_router)

# Register middleware directly
app.middleware("http")(add_request_id)
app.middleware("http")(log_requests)
app.middleware("http")(exception_logging_middleware)

# Register exception handlers
app.exception_handler(RequestValidationError)(validation_exception_handler)
app.exception_handler(ValidationError)(validation_exception_handler)
app.exception_handler(PermissionException)(permission_exception_handler)
app.exception_handler(NotFoundException)(not_found_exception_handler)
app.exception_handler(PaymentRequiredException)(payment_required_exception_handler)
app.exception_handler(UsageLimitExceededException)(usage_limit_exceeded_exception_handler)
app.exception_handler(InvalidStateError)(invalid_state_exception_handler)

# Register custom Airweave exception handlers
app.exception_handler(AirweaveException)(airweave_exception_handler)

# Default CORS origins - white labels and environment variables can extend this
CORS_ORIGINS = [
    "http://localhost:5173",
    "localhost:8001",
    "http://localhost:8080",
    "https://app.dev-airweave.com",
    "https://app.stg-airweave.com",
    "https://app.airweave.ai",
    "https://docs.airweave.ai",
    "localhost:3000",
]

if settings.ADDITIONAL_CORS_ORIGINS:
    additional_origins = settings.ADDITIONAL_CORS_ORIGINS.split(",")
    if settings.ENVIRONMENT == "local":
        CORS_ORIGINS.append("*")  # Allow all origins in local environment
    else:
        CORS_ORIGINS.extend(additional_origins)

# Add the dynamic CORS middleware that handles both default origins and white label specific origins
app.add_middleware(
    DynamicCORSMiddleware,
    default_origins=CORS_ORIGINS,
)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def show_docs_reference() -> HTMLResponse:
    """Root endpoint to display the API documentation.

    Returns:
    -------
        HTMLResponse: The HTML content to display the API documentation.

    """
    html_content = """
<!DOCTYPE html>
<html>
    <head>
        <title>Airweave API</title>
    </head>
    <body>
        <h1>Welcome to the Airweave API</h1>
        <p>Please visit the <a href="https://docs.airweave.ai">docs</a> for more information.</p>
    </body>
</html>
    """
    return HTMLResponse(content=html_content)
