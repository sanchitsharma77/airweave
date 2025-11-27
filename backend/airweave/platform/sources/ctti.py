"""CTTI source implementation.

This source connects to the AACT Clinical Trials PostgreSQL database, queries the nct_id column
from the studies table, and creates WebEntity instances with ClinicalTrials.gov URLs.
"""

import asyncio
import random
from typing import Any, AsyncGenerator, Dict, Optional, Union

import asyncpg

from airweave.platform.configs.auth import CTTIAuthConfig
from airweave.platform.decorators import source
from airweave.platform.entities.ctti import CTTIWebEntity
from airweave.platform.sources._base import BaseSource
from airweave.schemas.source_connection import AuthenticationMethod


@source(
    name="CTTI AACT",
    short_name="ctti",
    auth_methods=[AuthenticationMethod.DIRECT],
    oauth_type=None,
    auth_config_class="CTTIAuthConfig",
    config_class="CTTIConfig",
    labels=["Clinical Trials", "Database"],
    supports_continuous=False,
)
class CTTISource(BaseSource):
    """CTTI source connector integrates with the AACT PostgreSQL database to extract trials.

    Connects to the Aggregate Analysis of ClinicalTrials.gov database.
    Creates web entities that link to ClinicalTrials.gov pages.
    """

    # Hardcoded AACT database connection details
    AACT_HOST = "aact-db.ctti-clinicaltrials.org"
    AACT_PORT = 5432
    AACT_DATABASE = "aact"
    AACT_SCHEMA = "ctgov"
    AACT_TABLE = "studies"

    def __init__(self):
        """Initialize the CTTI source."""
        super().__init__()
        self.pool: Optional[asyncpg.Pool] = None

    @classmethod
    async def create(
        cls,
        credentials: Union[Dict[str, Any], CTTIAuthConfig],
        config: Optional[Dict[str, Any]] = None,
    ) -> "CTTISource":
        """Create a new CTTI source instance.

        Args:
            credentials: CTTIAuthConfig object or dictionary containing AACT database credentials:
                - username: Username for AACT database
                - password: Password for AACT database
            config: Optional configuration parameters:
                - limit: Maximum number of studies to fetch (default: 10000)
                - skip: Number of studies to skip for pagination (default: 0)
        """
        instance = cls()
        instance.credentials = credentials
        instance.config = config or {}
        return instance

    def _get_credential(self, key: str) -> str:
        """Get a credential value from either dict or config object.

        Args:
            key: The credential key to retrieve

        Returns:
            The credential value

        Raises:
            ValueError: If the credential is missing or empty
        """
        # Try to get from object attribute first (CTTIAuthConfig)
        value = getattr(self.credentials, key, None)

        # If not found and credentials is a dict, try dict access
        if value is None and isinstance(self.credentials, dict):
            value = self.credentials.get(key)

        # Validate the value exists and is not empty
        if not value:
            raise ValueError(f"Missing or empty credential: {key}")

        return value

    async def _retry_with_backoff(self, func, *args, max_retries: int = 3, **kwargs):
        """Retry a function with exponential backoff.

        Args:
            func: The async function to retry
            *args: Arguments to pass to the function
            max_retries: Maximum number of retry attempts
            **kwargs: Keyword arguments to pass to the function

        Returns:
            The result of the function call

        Raises:
            The last exception if all retries fail
        """
        last_exception = None

        for attempt in range(max_retries + 1):  # +1 for initial attempt
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                error_type = type(e).__name__
                error_msg = str(e)

                # Don't retry on certain permanent errors
                if isinstance(
                    e,
                    (
                        asyncpg.InvalidPasswordError,
                        asyncpg.InvalidCatalogNameError,
                        ValueError,
                    ),
                ):
                    self.logger.error(f"Non-retryable database error: {error_type}: {error_msg}")
                    raise e

                if attempt < max_retries:
                    # Calculate delay with exponential backoff and jitter
                    base_delay = 2**attempt  # 1s, 2s, 4s
                    jitter = random.uniform(0.1, 0.5)
                    delay = base_delay + jitter

                    self.logger.warning(
                        f"Database operation attempt {attempt + 1}/{max_retries + 1} failed with "
                        f"{error_type}: {error_msg}. Retrying in {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(
                        f"All {max_retries + 1} database operation attempts failed. "
                        f"Final error {error_type}: {error_msg}"
                    )

        raise last_exception

    async def _ensure_pool(self) -> asyncpg.Pool:
        """Ensure connection pool is initialized and return it.

        Creates a per-instance pool to ensure proper credential isolation
        between different organizations/syncs.
        """
        if not self.pool:
            username = self._get_credential("username")
            password = self._get_credential("password")

            self.logger.debug("Creating CTTI connection pool")
            self.pool = await asyncpg.create_pool(
                host=self.AACT_HOST,
                port=self.AACT_PORT,
                user=username,
                password=password,
                database=self.AACT_DATABASE,
                min_size=1,
                max_size=3,  # Conservative limit for public DB
                timeout=30.0,
                command_timeout=60.0,
            )
            self.logger.debug("CTTI connection pool created successfully")

        return self.pool

    async def _close_pool(self) -> None:
        """Close the connection pool if it exists."""
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def generate_entities(self) -> AsyncGenerator[CTTIWebEntity, None]:
        """Generate WebEntity instances for each nct_id in the AACT studies table."""
        try:
            pool = await self._ensure_pool()

            limit = self.config.get("limit", 10000)
            skip = self.config.get("skip", 0)

            query = f"""
                SELECT nct_id
                FROM "{self.AACT_SCHEMA}"."{self.AACT_TABLE}"
                WHERE nct_id IS NOT NULL
                ORDER BY nct_id
                LIMIT {limit}
                OFFSET {skip}
            """

            async def _execute_query():
                async with pool.acquire() as conn:
                    self.logger.debug(
                        f"Fetching up to {limit} clinical trials from AACT (offset: {skip})"
                    )
                    records = await conn.fetch(query)
                    self.logger.debug(f"Fetched {len(records)} clinical trial records")
                    return records

            records = await self._retry_with_backoff(_execute_query)

            self.logger.debug(f"Processing {len(records)} records into entities")
            entities_created = 0

            for record in records:
                nct_id = record["nct_id"]

                if not nct_id or not str(nct_id).strip():
                    continue

                clean_nct_id = str(nct_id).strip()

                entity = CTTIWebEntity(
                    nct_id=clean_nct_id,
                    name=f"Clinical Trial {clean_nct_id}",
                    crawl_url=f"https://clinicaltrials.gov/study/{clean_nct_id}",
                    breadcrumbs=[],
                )

                entities_created += 1

                if entities_created % 100 == 0:
                    self.logger.debug(f"Created {entities_created}/{len(records)} CTTI entities")

                # Yield control periodically to prevent blocking the event loop
                if entities_created % 10 == 0:
                    await asyncio.sleep(0)

                yield entity

            self.logger.debug(f"Completed creating {entities_created} CTTI entities")

        except Exception as e:
            self.logger.error(f"Error in CTTI generate_entities: {e}")
            raise
        finally:
            await self._close_pool()

    async def validate(self) -> bool:
        """Verify CTTI DB credentials and basic access by running a tiny query."""
        try:
            pool = await self._ensure_pool()

            async def _ping():
                async with pool.acquire() as conn:
                    await conn.fetchval(
                        f'SELECT 1 FROM "{self.AACT_SCHEMA}"."{self.AACT_TABLE}" LIMIT 1'
                    )

            await self._retry_with_backoff(_ping, max_retries=2)
            return True

        except (asyncpg.InvalidPasswordError, asyncpg.InvalidCatalogNameError, ValueError) as e:
            self.logger.error(f"CTTI validation failed (credentials/config): {e}")
            return False
        except Exception as e:
            self.logger.error(f"CTTI validation encountered an error: {e}")
            return False
        finally:
            await self._close_pool()
