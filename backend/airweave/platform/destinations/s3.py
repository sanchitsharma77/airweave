"""S3-compatible storage destination for event streaming.

Supports AWS S3, MinIO, LocalStack, Cloudflare R2, or any S3 API-compatible service.
Writes entities as JSONL files for downstream processing and archival.
"""

import json
import uuid
from datetime import datetime
from typing import Optional
from uuid import UUID

try:
    import aioboto3  # type: ignore
    from botocore.exceptions import ClientError, NoCredentialsError  # type: ignore
except ImportError:
    aioboto3 = None  # type: ignore
    ClientError = Exception  # type: ignore
    NoCredentialsError = Exception  # type: ignore

from airweave.core.logging import ContextualLogger
from airweave.core.logging import logger as default_logger
from airweave.platform.configs.auth import S3AuthConfig
from airweave.platform.decorators import destination
from airweave.platform.destinations._base import BaseDestination
from airweave.platform.entities._base import ChunkEntity


@destination("S3", "s3", config_class=S3AuthConfig, supports_vector=False)
class S3Destination(BaseDestination):
    """S3-compatible storage destination for event streaming.

    Data Organization:
        {bucket}/{prefix}/collections/{collection_id}/
            ├── entities/{timestamp}_{batch_id}.jsonl
            └── deletions/{timestamp}_{batch_id}.jsonl

    Note: Uses aioboto3 for true async S3 operations.
          Relies on EntityProcessor batching - no custom buffering.
    """

    def __init__(self):
        """Initialize S3 destination."""
        super().__init__()
        self.collection_id: UUID | None = None
        self.organization_id: UUID | None = None
        self.bucket_name: str | None = None
        self.bucket_prefix: str = "airweave-outbound/"
        self.session: aioboto3.Session | None = None
        # Store connection config for creating clients
        self._endpoint_url: str | None = None
        self._access_key_id: str | None = None
        self._secret_access_key: str | None = None
        self._region: str = "us-east-1"
        self._use_ssl: bool = True

    @classmethod
    async def create(
        cls,
        collection_id: UUID,
        organization_id: Optional[UUID] = None,
        logger: Optional[ContextualLogger] = None,
    ) -> "S3Destination":
        """Create and configure S3 destination.

        Args:
            collection_id: Collection UUID
            organization_id: Organization UUID (required for loading credentials)
            logger: Logger instance

        Returns:
            Configured S3Destination instance
        """
        if aioboto3 is None:
            raise ImportError("aioboto3 is required for S3 destination")

        instance = cls()
        instance.set_logger(logger or default_logger)
        instance.collection_id = collection_id
        instance.organization_id = organization_id

        # Load credentials from database (org-specific S3 connection)
        credentials = await cls.get_credentials(organization_id=organization_id)
        if not credentials:
            raise ValueError(
                f"S3 credentials not found for organization {organization_id}. "
                "Configure S3 connection in organization settings."
            )

        instance.bucket_name = credentials.bucket_name
        instance.bucket_prefix = credentials.bucket_prefix
        instance._endpoint_url = credentials.endpoint_url
        instance._access_key_id = credentials.aws_access_key_id
        instance._secret_access_key = credentials.aws_secret_access_key
        instance._region = credentials.aws_region
        instance._use_ssl = credentials.use_ssl
        instance.session = aioboto3.Session()
        await instance._test_connection()

        return instance

    async def _test_connection(self) -> None:
        """Test S3 connection by checking if bucket exists."""
        try:
            async with self.session.client(
                "s3",
                endpoint_url=self._endpoint_url,
                aws_access_key_id=self._access_key_id,
                aws_secret_access_key=self._secret_access_key,
                region_name=self._region,
                use_ssl=self._use_ssl,
            ) as s3:
                await s3.head_bucket(Bucket=self.bucket_name)

            self.logger.info(
                f"Connected to S3 bucket: {self.bucket_name} "
                f"(endpoint: {self._endpoint_url or 'AWS S3'})"
            )
        except NoCredentialsError as e:
            raise ConnectionError(f"S3 credentials not configured: {e}") from e
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "404":
                raise ConnectionError(f"S3 bucket '{self.bucket_name}' does not exist") from e
            elif error_code == "403":
                raise ConnectionError(f"Access denied to S3 bucket '{self.bucket_name}'") from e
            raise ConnectionError(f"Failed to connect to S3: {e}") from e

    async def setup_collection(self, vector_size: int | None = None) -> None:
        """No-op for S3 - paths created on write."""
        pass

    async def insert(self, entity: ChunkEntity) -> None:
        """Single entity insert - delegates to bulk_insert."""
        await self.bulk_insert([entity])

    async def bulk_insert(self, entities: list[ChunkEntity]) -> None:
        """Write entities as JSONL file to S3.

        EntityProcessor already batches entities, so we just write whatever we receive.
        """
        if not entities:
            return

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        batch_id = str(uuid.uuid4())[:8]
        filename = f"{timestamp}_{batch_id}.jsonl"
        key = f"{self.bucket_prefix}collections/{self.collection_id}/entities/{filename}"

        # Convert entities to JSONL
        jsonl_content = "\n".join(
            json.dumps(e.to_storage_dict(), default=self._json_serializer) for e in entities
        )

        # Write to S3
        try:
            async with self.session.client(
                "s3",
                endpoint_url=self._endpoint_url,
                aws_access_key_id=self._access_key_id,
                aws_secret_access_key=self._secret_access_key,
                region_name=self._region,
                use_ssl=self._use_ssl,
            ) as s3:
                await s3.put_object(
                    Bucket=self.bucket_name,
                    Key=key,
                    Body=jsonl_content.encode("utf-8"),
                    ContentType="application/x-ndjson",
                    Metadata={
                        "collection_id": str(self.collection_id),
                        "entity_count": str(len(entities)),
                    },
                )

            self.logger.info(f"Wrote {len(entities)} entities to S3: {key}")
        except Exception as e:
            self.logger.error(f"Failed to write to S3: {e}", exc_info=True)
            raise

    async def delete(self, db_entity_id: UUID) -> None:
        """Record deletion event."""
        await self._write_deletion_events([{"db_entity_id": str(db_entity_id)}])

    async def bulk_delete(self, entity_ids: list[str], sync_id: UUID) -> None:
        """Record bulk deletion events."""
        events = [{"entity_id": eid, "sync_id": str(sync_id)} for eid in entity_ids]
        await self._write_deletion_events(events)

    async def bulk_delete_by_parent_id(self, parent_id: str, sync_id: UUID) -> None:
        """Record parent deletion event."""
        await self._write_deletion_events([{"parent_id": parent_id, "sync_id": str(sync_id)}])

    async def _write_deletion_events(self, events: list[dict]) -> None:
        """Write deletion events to S3."""
        if not events:
            return

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        batch_id = str(uuid.uuid4())[:8]
        filename = f"{timestamp}_{batch_id}.jsonl"
        key = f"{self.bucket_prefix}collections/{self.collection_id}/deletions/{filename}"

        # Add metadata and convert to JSONL
        for event in events:
            event["action"] = "delete"
            event["deleted_at"] = datetime.utcnow().isoformat()

        jsonl_content = "\n".join(json.dumps(e, default=self._json_serializer) for e in events)

        try:
            async with self.session.client(
                "s3",
                endpoint_url=self._endpoint_url,
                aws_access_key_id=self._access_key_id,
                aws_secret_access_key=self._secret_access_key,
                region_name=self._region,
                use_ssl=self._use_ssl,
            ) as s3:
                await s3.put_object(
                    Bucket=self.bucket_name,
                    Key=key,
                    Body=jsonl_content.encode("utf-8"),
                    ContentType="application/x-ndjson",
                )

            self.logger.info(f"Wrote {len(events)} deletion events to S3: {key}")
        except Exception as e:
            self.logger.error(f"Failed to write deletion events: {e}", exc_info=True)
            raise

    async def delete_by_sync_id(self, sync_id: UUID) -> None:
        """Not applicable for S3 (append-only)."""
        pass

    async def search(self, query_vector: list[float]) -> None:
        """S3 doesn't support search."""
        raise NotImplementedError("S3 destination doesn't support search")

    async def has_keyword_index(self) -> bool:
        """S3 doesn't have keyword index."""
        return False

    @classmethod
    async def get_credentials(cls, organization_id: Optional[UUID] = None) -> S3AuthConfig | None:
        """Get S3 credentials from database for organization.

        Args:
            organization_id: Organization UUID to load credentials for

        Returns:
            S3AuthConfig if found, None otherwise
        """
        if not organization_id:
            return None

        from sqlalchemy import and_, select

        from airweave import crud
        from airweave.core.security import decrypt_data
        from airweave.db.session import get_db_context
        from airweave.models.connection import Connection

        async with get_db_context() as db:
            # Find S3 connection for this organization
            stmt = select(Connection).where(
                and_(
                    Connection.organization_id == organization_id,
                    Connection.short_name == "s3",
                    Connection.integration_type == "DESTINATION",
                )
            )
            result = await db.execute(stmt)
            connection = result.scalar_one_or_none()

            if not connection or not connection.integration_credential_id:
                return None

            # Load and decrypt credentials
            cred = await crud.integration_credential.get(db, connection.integration_credential_id)
            if not cred:
                return None

            # Decrypt and return as S3AuthConfig
            decrypted_data = decrypt_data(cred.encrypted_data)
            return S3AuthConfig(**decrypted_data)

    @staticmethod
    def _json_serializer(obj):
        """JSON serializer for special types."""
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="replace")
        return str(obj)
