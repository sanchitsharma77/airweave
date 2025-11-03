import asyncio
import time
import uuid
from typing import Any, Dict, List

import httpx
from monke.bongos.base_bongo import BaseBongo
from monke.generation.hubspot import generate_hubspot_contact
from monke.utils.logging import get_logger

HUBSPOT_API = "https://api.hubapi.com"


class HubSpotBongo(BaseBongo):
    """Creates/updates/deletes HubSpot Contacts using Private App token."""

    connector_type = "hubspot"

    def __init__(self, credentials: Dict[str, Any], **kwargs):
        super().__init__(credentials)
        self.access_token: str = credentials["access_token"]
        self.entity_count: int = int(kwargs.get("entity_count", 3))
        self.openai_model: str = kwargs.get("openai_model", "gpt-4.1-mini")
        self.rate_limit_delay = float(kwargs.get("rate_limit_delay_ms", 800)) / 1000.0
        self.logger = get_logger("hubspot_bongo")
        self._contacts: List[Dict[str, Any]] = []
        self._last_req = 0.0

    async def create_entities(self) -> List[Dict[str, Any]]:
        self.logger.info(f"🥁 Creating {self.entity_count} HubSpot contacts")
        out: List[Dict[str, Any]] = []

        # Generate all contacts in parallel
        tokens = [str(uuid.uuid4())[:8] for _ in range(self.entity_count)]

        async def generate_contact_data(token: str):
            c = await generate_hubspot_contact(self.openai_model, token)
            return token, c

        # Generate all content in parallel
        gen_results = await asyncio.gather(*[generate_contact_data(token) for token in tokens])

        # Create contacts sequentially to respect API rate limits
        async with httpx.AsyncClient(base_url=HUBSPOT_API, timeout=30) as client:
            for token, c in gen_results:
                await self._pace()
                # Embed token in multiple fields for better vector search recall
                # Token in company name is most reliable for vector search
                payload = {
                    "properties": {
                        "email": c.email,
                        "firstname": c.firstname,
                        "lastname": c.lastname,
                        "company": f"{c.company or 'Monke Test Corp'} [{token}]",  # Token in company
                        **({"phone": c.phone} if c.phone else {}),
                        **({"address": c.address} if c.address else {}),
                        **({"city": c.city} if c.city else {}),
                        **({"state": c.state} if c.state else {}),
                        **({"zip": c.zip} if c.zip else {}),
                    }
                }
                r = await client.post(
                    "/crm/v3/objects/contacts",
                    headers=self._hdrs(),
                    json=payload,
                )
                if r.status_code not in (200, 201):
                    self.logger.error(f"HubSpot create failed {r.status_code}: {r.text}")
                r.raise_for_status()
                data = r.json()
                contact_id = data.get("id")
                ent = {
                    "type": "contact",
                    "id": contact_id,
                    "name": f"{c.firstname} {c.lastname}",
                    "token": token,
                    "expected_content": token,
                    "path": f"hubspot/contact/{contact_id}",
                }
                out.append(ent)
                self._contacts.append(ent)
                self.created_entities.append({"id": contact_id, "name": ent["name"]})
        return out

    async def update_entities(self) -> List[Dict[str, Any]]:
        if not self._contacts:
            return []
        self.logger.info("🥁 Updating some HubSpot contacts")
        updated: List[Dict[str, Any]] = []
        async with httpx.AsyncClient(base_url=HUBSPOT_API, timeout=30) as client:
            for ent in self._contacts[: min(3, len(self._contacts))]:
                await self._pace()
                # Update phone but preserve token in company name
                token = ent.get("token", "")
                r = await client.patch(
                    f"/crm/v3/objects/contacts/{ent['id']}",
                    headers=self._hdrs(),
                    json={"properties": {
                        "phone": "+1-555-0100",
                        "company": f"Monke QA Updated [{token}]"  # Preserve token
                    }},
                )
                r.raise_for_status()
                updated.append({**ent, "updated": True})
        return updated

    async def delete_entities(self) -> List[str]:
        return await self.delete_specific_entities(self._contacts)

    async def delete_specific_entities(self, entities: List[Dict[str, Any]]) -> List[str]:
        self.logger.info(f"🥁 Deleting {len(entities)} HubSpot contacts")
        deleted: List[str] = []
        async with httpx.AsyncClient(base_url=HUBSPOT_API, timeout=30) as client:
            for ent in entities:
                try:
                    await self._pace()
                    r = await client.delete(
                        f"/crm/v3/objects/contacts/{ent['id']}", headers=self._hdrs()
                    )
                    if r.status_code in (200, 204):
                        deleted.append(ent["id"])
                    else:
                        self.logger.warning(f"Delete failed {r.status_code}: {r.text}")
                except Exception as e:
                    self.logger.warning(f"Delete error {ent['id']}: {e}")
        return deleted

    async def cleanup(self):
        """Comprehensive cleanup of all test HubSpot contacts."""
        self.logger.info("🧹 Starting comprehensive HubSpot cleanup")

        cleanup_stats = {"contacts_deleted": 0, "errors": 0}

        try:
            # First, delete current session contacts
            if self._contacts:
                self.logger.info(f"🗑️ Cleaning up {len(self._contacts)} current session contacts")
                deleted = await self.delete_specific_entities(self._contacts)
                cleanup_stats["contacts_deleted"] += len(deleted)
                self._contacts.clear()

            # Search for any remaining monke test contacts
            await self._cleanup_orphaned_test_contacts(cleanup_stats)

            self.logger.info(
                f"🧹 Cleanup completed: {cleanup_stats['contacts_deleted']} contacts deleted, "
                f"{cleanup_stats['errors']} errors"
            )
        except Exception as e:
            self.logger.error(f"❌ Error during comprehensive cleanup: {e}")

    async def _cleanup_orphaned_test_contacts(self, stats: Dict[str, Any]):
        """Find and delete orphaned test contacts from previous runs."""
        try:
            async with httpx.AsyncClient(base_url=HUBSPOT_API, timeout=30) as client:
                # Search for contacts with test patterns in name or email
                r = await client.get(
                    "/crm/v3/objects/contacts", headers=self._hdrs(), params={"limit": 100}
                )

                if r.status_code == 200:
                    contacts = r.json().get("results", [])
                    test_contacts = []

                    for contact in contacts:
                        props = contact.get("properties", {})
                        email = props.get("email", "").lower()
                        firstname = props.get("firstname", "").lower()
                        lastname = props.get("lastname", "").lower()

                        # Check if this looks like a test contact
                        if (
                            any(pattern in email for pattern in ["test", "monke", "example.com"])
                            or any(pattern in firstname for pattern in ["test", "monke", "demo"])
                            or any(pattern in lastname for pattern in ["test", "monke", "demo"])
                        ):
                            test_contacts.append(contact)

                    if test_contacts:
                        self.logger.info(
                            f"🔍 Found {len(test_contacts)} potential test contacts to clean"
                        )
                        for contact in test_contacts:
                            try:
                                await self._pace()
                                del_r = await client.delete(
                                    f"/crm/v3/objects/contacts/{contact['id']}",
                                    headers=self._hdrs(),
                                )
                                if del_r.status_code in (204, 202):
                                    stats["contacts_deleted"] += 1
                                    props = contact.get("properties", {})
                                    self.logger.info(
                                        f"✅ Deleted orphaned contact: "
                                        f"{props.get('email', 'unknown')}"
                                    )
                                else:
                                    stats["errors"] += 1
                            except Exception as e:
                                stats["errors"] += 1
                                self.logger.warning(
                                    f"⚠️ Failed to delete contact {contact['id']}: {e}"
                                )
        except Exception as e:
            self.logger.warning(f"⚠️ Could not search for orphaned contacts: {e}")

    def _hdrs(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

    async def _pace(self):
        now = time.time()
        if (delta := now - self._last_req) < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - delta)
        self._last_req = time.time()
