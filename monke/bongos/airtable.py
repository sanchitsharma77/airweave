"""Airtable-specific bongo implementation.

Creates, updates, and deletes test records via the real Airtable API.
"""

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional

import httpx
from monke.bongos.base_bongo import BaseBongo
from monke.utils.logging import get_logger


class AirtableBongo(BaseBongo):
    """Bongo for Airtable that creates bases, tables, and records for end-to-end testing.

    - Uses OAuth access token for authentication
    - Embeds a short token in record fields for verification
    - Creates a temporary base and table to keep test data scoped and easy to clean up
    """

    connector_type = "airtable"

    API_BASE = "https://api.airtable.com/v0"

    def __init__(self, credentials: Dict[str, Any], **kwargs):
        """Initialize the Airtable bongo.

        Args:
            credentials: Dict with at least "access_token" (OAuth token)
            **kwargs: Configuration from config file
        """
        super().__init__(credentials)
        self.access_token: str = credentials["access_token"]
        self.entity_count: int = int(kwargs.get("entity_count", 3))
        self.openai_model: str = kwargs.get("openai_model", "gpt-4.1-mini")
        self.max_concurrency: int = int(kwargs.get("max_concurrency", 1))
        # Use rate_limit_delay_ms from config if provided, otherwise default to 250ms
        rate_limit_ms = int(kwargs.get("rate_limit_delay_ms", 250))
        self.rate_limit_delay: float = rate_limit_ms / 1000.0

        # Runtime state
        self._base_id: Optional[str] = None
        self._table_id: Optional[str] = None
        self._table_name: str = "MonkeTestTable"
        self._records: List[Dict[str, Any]] = []
        self._comments: List[Dict[str, Any]] = []  # Track created comments

        # Pacing
        self.last_request_time = 0.0
        self._rate_limit_lock = asyncio.Lock()

        self.logger = get_logger("airtable_bongo")

    async def create_entities(self) -> List[Dict[str, Any]]:
        """Create records in a temporary Airtable base and table.

        This tests the full entity hierarchy:
        - User: Automatic via whoami endpoint (tested by source)
        - Base: Uses existing accessible base (API doesn't allow base creation)
        - Table: Creates a test table with defined schema (tracked and verified)
        - Records: Creates test records with embedded tokens
        - Comments: Creates comments on each record with tokens
        - Attachments: Not tested (requires file upload, can add later)

        Returns a list of created entity descriptors used by the test flow.
        """
        self.logger.info(
            f"🥁 Creating {self.entity_count} Airtable records with table and comments"
        )

        # First, create a test base (or use existing)
        await self._ensure_base()

        # Then create a test table in that base
        await self._ensure_table()
        self.logger.info(f"✅ Table created: {self._table_name} ({self._table_id})")

        from monke.generation.airtable import generate_airtable_record

        entities: List[Dict[str, Any]] = []
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async with httpx.AsyncClient() as client:

            async def create_one() -> Optional[Dict[str, Any]]:
                async with semaphore:
                    try:
                        await self._rate_limit()
                        token = str(uuid.uuid4())[:8]
                        self.logger.info(
                            f"🔨 Generating content for record with token: {token}"
                        )
                        fields, _, comments = await generate_airtable_record(
                            self.openai_model, token
                        )
                        self.logger.info(
                            f"📝 Generated record: '{fields.get('Name', '')[:50]}...' "
                            f"with {len(comments)} comments"
                        )

                        # Create record
                        resp = await client.post(
                            f"{self.API_BASE}/{self._base_id}/{self._table_id}",
                            headers=self._headers(),
                            json={"fields": fields},
                        )

                        if resp.status_code not in (200, 201):
                            error_data = resp.text
                            try:
                                error_json = resp.json()
                                error_data = error_json
                            except Exception:
                                pass
                            self.logger.error(
                                f"Failed to create record: {resp.status_code} - {error_data}"
                            )

                        resp.raise_for_status()
                        record = resp.json()
                        record_id = record.get("id")

                        # Add generated comments to the record
                        for comment_text in comments:
                            await self._rate_limit()
                            try:
                                comment_resp = await client.post(
                                    f"{self.API_BASE}/{self._base_id}/{self._table_id}/{record_id}/comments",
                                    headers=self._headers(),
                                    json={"text": comment_text},
                                )
                                if comment_resp.status_code in (200, 201):
                                    comment = comment_resp.json()
                                    self._comments.append(
                                        {
                                            "id": comment.get("id"),
                                            "record_id": record_id,
                                            "token": token,
                                            "text": comment_text,
                                        }
                                    )
                                    self.logger.debug(
                                        f"Added comment to record {record_id}: "
                                        f"'{comment_text[:50]}...'"
                                    )
                                else:
                                    self.logger.warning(
                                        f"Failed to create comment: {comment_resp.status_code}"
                                    )
                            except Exception as ex:
                                self.logger.warning(
                                    f"Failed to add comment to {record_id}: {ex}"
                                )

                        # Entity descriptor used by generic verification
                        return {
                            "type": "record",
                            "id": record_id,
                            "name": fields.get("Name", ""),
                            "token": token,
                            "expected_content": token,
                            "path": f"airtable/record/{record_id}",
                        }
                    except Exception as e:
                        self.logger.error(
                            f"❌ Error in create_one: {type(e).__name__}: {str(e)}"
                        )
                        raise

            # Create all records in parallel
            tasks = [create_one() for _ in range(self.entity_count)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results and handle any exceptions
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.logger.error(f"Failed to create record {i + 1}: {result}")
                    raise result
                elif result:
                    entities.append(result)
                    self._records.append(result)
                    self.logger.info(
                        f"✅ Created record {i + 1}/{self.entity_count}: {result['name'][:50]}..."
                    )

        self.created_entities = entities

        # Log summary of what was created
        self.logger.info("📊 Creation summary:")
        self.logger.info(f"  - Base: {self._base_id}")
        self.logger.info(f"  - Table: {self._table_name} ({self._table_id})")
        self.logger.info(f"  - Records: {len(entities)}")
        self.logger.info(f"  - Comments: {len(self._comments)}")
        self.logger.info("  - Attachments: 0 (not tested)")

        return entities

    async def update_entities(self) -> List[Dict[str, Any]]:
        """Update a small subset of records by regenerating fields with same token."""
        self.logger.info("🥁 Updating some Airtable records")
        if not self._records:
            return []

        from monke.generation.airtable import generate_airtable_record

        updated_entities: List[Dict[str, Any]] = []
        count = min(2, len(self._records))

        async with httpx.AsyncClient() as client:
            for i in range(count):
                await self._rate_limit()
                record = self._records[i]
                fields, _, comments = await generate_airtable_record(
                    self.openai_model, record["token"]
                )
                # Note: We don't re-add comments during updates, just update the record fields
                resp = await client.patch(
                    f"{self.API_BASE}/{self._base_id}/{self._table_id}/{record['id']}",
                    headers=self._headers(),
                    json={"fields": fields},
                )
                resp.raise_for_status()
                updated_entities.append(
                    {
                        **record,
                        "name": fields.get("Name", ""),
                        "expected_content": record["token"],
                    }
                )

        return updated_entities

    async def delete_entities(self) -> List[str]:
        """Delete all created records and the temporary base."""
        self.logger.info("🥁 Deleting all Airtable test entities")
        deleted_ids = await self.delete_specific_entities(self.created_entities)
        # Note: We don't delete the base here since Airtable doesn't provide
        # a programmatic way to delete bases via API
        return deleted_ids

    async def delete_specific_entities(
        self, entities: List[Dict[str, Any]]
    ) -> List[str]:
        """Delete provided list of records by id."""
        self.logger.info(f"🥁 Deleting {len(entities)} Airtable records")
        deleted: List[str] = []
        async with httpx.AsyncClient() as client:
            for e in entities:
                try:
                    await self._rate_limit()
                    r = await client.delete(
                        f"{self.API_BASE}/{self._base_id}/{self._table_id}/{e['id']}",
                        headers=self._headers(),
                    )
                    if r.status_code in (200, 204):
                        deleted.append(e["id"])
                    else:
                        self.logger.warning(
                            f"Delete failed for {e.get('id')}: {r.status_code} - {r.text}"
                        )
                except Exception as ex:
                    self.logger.warning(f"Delete error for {e.get('id')}: {ex}")
        return deleted

    async def cleanup(self):
        """Comprehensive cleanup of all monke test data.

        Note: Airtable API doesn't provide endpoints to delete bases programmatically.
        We clean up records (which also deletes associated comments).
        The test table and base need to be manually deleted from Airtable UI.
        """
        self.logger.info("🧹 Starting comprehensive Airtable cleanup")

        cleanup_stats = {"records_deleted": 0, "comments_deleted": 0, "errors": 0}

        try:
            # Clean up current session data first
            if self._records:
                self.logger.info(
                    f"🗑️ Cleaning up {len(self._records)} current session records "
                    f"(and {len(self._comments)} comments)"
                )
                deleted = await self.delete_specific_entities(self._records)
                cleanup_stats["records_deleted"] += len(deleted)
                # Comments are automatically deleted with records
                cleanup_stats["comments_deleted"] = len(self._comments)

            # Log cleanup summary
            self.logger.info(
                f"🧹 Cleanup completed: {cleanup_stats['records_deleted']} records deleted, "
                f"{cleanup_stats['comments_deleted']} comments deleted (automatic), "
                f"{cleanup_stats['errors']} errors"
            )
            self.logger.warning(
                "⚠️ Note: Test table and base need manual cleanup from Airtable UI. "
                f"Table: {self._table_name} ({self._table_id}), Base: {self._base_id}"
            )

        except Exception as e:
            self.logger.error(f"❌ Error during comprehensive cleanup: {e}")

    async def _ensure_base(self):
        """Create a test base for monke testing.

        Note: Base creation via API requires special permissions.
        For now, we expect a base to be pre-configured or we'll use
        an existing accessible base.
        """
        if self._base_id:
            return

        # For testing, we'll list bases and use the first accessible one
        # In production monke testing, you should configure a specific test base
        async with httpx.AsyncClient() as client:
            try:
                r = await client.get(
                    f"{self.API_BASE}/meta/bases",
                    headers=self._headers(),
                )
                r.raise_for_status()
                bases = r.json().get("bases", [])

                if not bases:
                    raise RuntimeError(
                        "No accessible Airtable bases found. "
                        "Please create a base and grant access to your OAuth app."
                    )

                # Use the first base
                self._base_id = bases[0]["id"]
                self.logger.info(
                    f"Using base {self._base_id} ({bases[0].get('name', 'Unknown')})"
                )

            except Exception as e:
                self.logger.error(f"Failed to find accessible base: {e}")
                raise

    async def _ensure_table(self):
        """Create a test table in the base."""
        if self._table_id:
            return

        table_name = f"monke-test-{str(uuid.uuid4())[:6]}"
        self._table_name = table_name

        async with httpx.AsyncClient() as client:
            # Create table with fields
            payload = {
                "description": "Monke test table - safe to delete",
                "fields": [
                    {"name": "Name", "type": "singleLineText"},
                    {"name": "Description", "type": "multilineText"},
                    {
                        "name": "Status",
                        "type": "singleSelect",
                        "options": {
                            "choices": [
                                {"name": "Todo"},
                                {"name": "In Progress"},
                                {"name": "Done"},
                            ]
                        },
                    },
                    {"name": "Tags", "type": "singleLineText"},
                    {"name": "Notes", "type": "multilineText"},
                ],
                "name": table_name,
            }

            r = await client.post(
                f"{self.API_BASE}/meta/bases/{self._base_id}/tables",
                headers=self._headers(),
                json=payload,
            )

            if r.status_code not in (200, 201):
                self.logger.error(f"Table create failed {r.status_code}: {r.text}")
            r.raise_for_status()

            self._table_id = r.json()["id"]
            self.logger.info(f"Created table {table_name} ({self._table_id})")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def _rate_limit(self):
        """Rate limiting to respect Airtable's 5 requests/second per base limit.

        Uses a lock to prevent race conditions when multiple tasks are running concurrently.
        """
        async with self._rate_limit_lock:
            now = time.time()
            delta = now - self.last_request_time
            if delta < self.rate_limit_delay:
                await asyncio.sleep(self.rate_limit_delay - delta)
            self.last_request_time = time.time()
