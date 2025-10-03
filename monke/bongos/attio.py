"""Attio-specific bongo implementation.

Creates, updates, and deletes test records via the real Attio API.
"""

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional

import httpx
from monke.bongos.base_bongo import BaseBongo
from monke.utils.logging import get_logger


class AttioBongo(BaseBongo):
    """Bongo for Attio that creates companies, people, and notes for end-to-end testing.

    - Uses an API key for authentication
    - Embeds a short token in record descriptions/notes for verification
    - Works with standard Attio objects (Companies and People)
    """

    connector_type = "attio"

    API_BASE = "https://api.attio.com/v2"

    def __init__(self, credentials: Dict[str, Any], **kwargs):
        """Initialize the Attio bongo.

        Args:
            credentials: Dict with "api_key" (direct auth) or "access_token" (OAuth/Composio)
            **kwargs: Configuration from config file
        """
        super().__init__(credentials)

        # Attio supports both API key (direct) and OAuth (via Composio)
        # Direct auth: api_key
        # Composio OAuth: access_token
        self.api_key: str = (
            credentials.get("api_key")
            or credentials.get("access_token")  # OAuth from Composio
            or credentials.get("generic_api_key")  # Alternative API key field
        )

        if not self.api_key:
            available_fields = list(credentials.keys())
            raise ValueError(
                f"Missing authentication credentials. Expected 'api_key' (direct) or "
                f"'access_token' (OAuth/Composio). Available fields: {available_fields}"
            )
        self.entity_count: int = int(kwargs.get("entity_count", 3))
        self.openai_model: str = kwargs.get("openai_model", "gpt-4.1-mini")
        self.max_concurrency: int = int(kwargs.get("max_concurrency", 2))
        rate_limit_ms = int(kwargs.get("rate_limit_delay_ms", 300))
        self.rate_limit_delay: float = rate_limit_ms / 1000.0

        # Runtime state
        self._company_records: List[Dict[str, Any]] = []
        self._person_records: List[Dict[str, Any]] = []

        # Pacing
        self.last_request_time = 0.0

        self.logger = get_logger("attio_bongo")

    def _headers(self) -> Dict[str, str]:
        """Return headers for Attio API requests."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _rate_limit(self):
        """Simple rate limiting to avoid hitting API limits."""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    async def _ensure_workspace(self):
        """No-op: Attio API doesn't require workspace ID for record creation."""
        pass

    async def create_entities(self) -> List[Dict[str, Any]]:
        """Create companies and people in Attio with embedded tokens.

        Returns a list of created entity descriptors used by the test flow.
        """
        self.logger.info(f"🥁 Creating {self.entity_count} Attio companies and people")
        await self._ensure_workspace()

        from monke.generation.attio import (
            generate_attio_company,
            generate_attio_note,
            generate_attio_person,
        )

        entities: List[Dict[str, Any]] = []
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async with httpx.AsyncClient() as client:

            async def create_company() -> Optional[Dict[str, Any]]:
                """Create a single company record with a note."""
                async with semaphore:
                    try:
                        await self._rate_limit()
                        token = str(uuid.uuid4())[:8]
                        self.logger.info(f"🏢 Generating company with token: {token}")

                        company_data = await generate_attio_company(self.openai_model, token)
                        self.logger.info(f"📝 Generated company: '{company_data['name']}'")

                        # Create company record
                        # Attio uses a specific format for attribute values
                        # Note: Only using universally available fields
                        attributes = {
                            "name": [{"value": company_data["name"]}],
                            "domains": [{"domain": company_data["domain"]}],
                            "description": [{"value": company_data["description"]}],
                            # Skip categories - they must be pre-configured in the workspace
                        }

                        resp = await client.post(
                            f"{self.API_BASE}/objects/companies/records",
                            headers=self._headers(),
                            json={"data": {"values": attributes}},
                            timeout=20.0,
                        )

                        if resp.status_code not in (200, 201):
                            self.logger.error(
                                f"Failed to create company: {resp.status_code} - {resp.text}"
                            )
                        resp.raise_for_status()

                        record_data = resp.json()["data"]
                        record_id = record_data["id"]["record_id"]

                        self.logger.info(f"✅ Created company record: {record_id}")

                        # Note: Attio API doesn't support creating notes via REST API
                        # Notes can only be created through the UI

                        entity = {
                            "type": "company",
                            "id": record_id,
                            "name": company_data["name"],
                            "token": token,
                            "expected_content": token,
                            "object_id": "companies",
                        }

                        return entity

                    except Exception as e:
                        self.logger.error(f"❌ Error creating company: {type(e).__name__}: {str(e)}")
                        raise

            async def create_person() -> Optional[Dict[str, Any]]:
                """Create a single person record with a note."""
                async with semaphore:
                    try:
                        await self._rate_limit()
                        token = str(uuid.uuid4())[:8]
                        self.logger.info(f"👤 Generating person with token: {token}")

                        person_data = await generate_attio_person(self.openai_model, token)
                        self.logger.info(
                            f"📝 Generated person: '{person_data['first_name']} {person_data['last_name']}'"
                        )

                        # Create person record
                        # Note: Attio requires full_name format, not first/last separately
                        full_name = f"{person_data['first_name']} {person_data['last_name']}"
                        attributes = {
                            "name": [
                                {
                                    "full_name": full_name,
                                    "first_name": person_data["first_name"],
                                    "last_name": person_data["last_name"],
                                }
                            ],
                            "email_addresses": [{"email_address": person_data["email"]}],
                            "job_title": [{"value": person_data["title"]}],
                            "description": [{"value": person_data["bio"]}],
                        }

                        resp = await client.post(
                            f"{self.API_BASE}/objects/people/records",
                            headers=self._headers(),
                            json={"data": {"values": attributes}},
                            timeout=20.0,
                        )

                        if resp.status_code not in (200, 201):
                            self.logger.error(
                                f"Failed to create person: {resp.status_code} - {resp.text}"
                            )
                        resp.raise_for_status()

                        record_data = resp.json()["data"]
                        record_id = record_data["id"]["record_id"]

                        self.logger.info(f"✅ Created person record: {record_id}")

                        # Note: Attio API doesn't support creating notes via REST API
                        # Notes can only be created through the UI

                        entity = {
                            "type": "person",
                            "id": record_id,
                            "name": f"{person_data['first_name']} {person_data['last_name']}",
                            "token": token,
                            "expected_content": token,
                            "object_id": "people",
                        }

                        return entity

                    except Exception as e:
                        self.logger.error(f"❌ Error creating person: {type(e).__name__}: {str(e)}")
                        raise

            # Create both companies and people
            tasks = []
            for _ in range(self.entity_count):
                tasks.append(create_company())
                tasks.append(create_person())

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.logger.error(f"Failed to create entity {i + 1}: {result}")
                    raise result
                elif result:
                    entities.append(result)
                    if result["type"] == "company":
                        self._company_records.append(result)
                    else:
                        self._person_records.append(result)

        self.created_entities = entities
        self.logger.info(
            f"✅ Created {len(self._company_records)} companies and {len(self._person_records)} people"
        )
        return entities

    async def update_entities(self) -> List[Dict[str, Any]]:
        """Update a subset of records by regenerating their content with the same token."""
        self.logger.info("🥁 Updating some Attio records")
        if not self.created_entities:
            return []

        from monke.generation.attio import generate_attio_company, generate_attio_person

        updated_entities: List[Dict[str, Any]] = []
        count = min(2, len(self.created_entities))

        async with httpx.AsyncClient() as client:
            for i in range(count):
                entity = self.created_entities[i]
                await self._rate_limit()

                try:
                    if entity["type"] == "company":
                        company_data = await generate_attio_company(
                            self.openai_model, entity["token"]
                        )
                        attributes = {
                            "description": [{"value": company_data["description"]}],
                        }
                    else:  # person
                        person_data = await generate_attio_person(
                            self.openai_model, entity["token"]
                        )
                        attributes = {
                            "description": [{"value": person_data["bio"]}],
                        }

                    resp = await client.patch(
                        f"{self.API_BASE}/objects/{entity['object_id']}/records/{entity['id']}",
                        headers=self._headers(),
                        json={"data": {"values": attributes}},
                        timeout=20.0,
                    )
                    resp.raise_for_status()
                    updated_entities.append(entity)
                    self.logger.info(f"✅ Updated {entity['type']}: {entity['id']}")
                except Exception as e:
                    self.logger.error(f"Failed to update {entity['type']}: {e}")

        return updated_entities

    async def delete_entities(self) -> List[str]:
        """Delete all created records."""
        self.logger.info("🥁 Deleting all Attio test entities")
        return await self.delete_specific_entities(self.created_entities)

    async def delete_specific_entities(self, entities: List[Dict[str, Any]]) -> List[str]:
        """Delete provided list of records by id."""
        self.logger.info(f"🥁 Deleting {len(entities)} Attio records")
        deleted: List[str] = []

        async with httpx.AsyncClient() as client:
            for entity in entities:
                try:
                    await self._rate_limit()
                    resp = await client.delete(
                        f"{self.API_BASE}/objects/{entity['object_id']}/records/{entity['id']}",
                        headers=self._headers(),
                        timeout=20.0,
                    )
                    if resp.status_code in (200, 204, 404):
                        deleted.append(entity["id"])
                        self.logger.info(f"✅ Deleted {entity['type']}: {entity['id']}")
                    else:
                        self.logger.warning(
                            f"Unexpected status {resp.status_code} deleting {entity['id']}"
                        )
                except Exception as e:
                    self.logger.error(f"Failed to delete {entity['id']}: {e}")

        return deleted

    async def cleanup(self) -> None:
        """Clean up any test data (same as delete_entities for Attio)."""
        if self.created_entities:
            await self.delete_entities()
