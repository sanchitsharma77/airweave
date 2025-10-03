import asyncio
import time
import uuid
from typing import Any, Dict, List

import httpx
from monke.bongos.base_bongo import BaseBongo
from monke.generation.outlook_calendar import generate_outlook_event
from monke.utils.logging import get_logger

GRAPH = "https://graph.microsoft.com/v1.0"


class OutlookCalendarBongo(BaseBongo):
    connector_type = "outlook_calendar"

    def __init__(self, credentials: Dict[str, Any], **kwargs):
        super().__init__(credentials)
        self.access_token: str = credentials["access_token"]
        self.entity_count: int = int(kwargs.get("entity_count", 3))
        self.openai_model: str = kwargs.get("openai_model", "gpt-4.1-mini")
        self.rate_limit_delay = float(kwargs.get("rate_limit_delay_ms", 500)) / 1000.0
        self.logger = get_logger("outlook_calendar_bongo")
        self._events: List[Dict[str, Any]] = []
        self._last_req = 0.0

    async def create_entities(self) -> List[Dict[str, Any]]:
        self.logger.info(f"🥁 Creating {self.entity_count} calendar events")
        out: List[Dict[str, Any]] = []
        async with httpx.AsyncClient(base_url=GRAPH, timeout=30) as client:
            for _ in range(self.entity_count):
                await self._pace()
                token = uuid.uuid4().hex[:8]
                ev = await generate_outlook_event(self.openai_model, token)
                payload = {
                    "subject": ev.subject,
                    "body": {"contentType": "HTML", "content": ev.body_html},
                    "start": {"dateTime": ev.start_iso, "timeZone": ev.timezone},
                    "end": {"dateTime": ev.end_iso, "timeZone": ev.timezone},
                }
                r = await client.post("/me/events", headers=self._hdrs(), json=payload)
                if r.status_code not in (200, 201):
                    self.logger.error(f"Create event failed {r.status_code}: {r.text}")
                r.raise_for_status()
                data = r.json()
                ent = {
                    "type": "event",
                    "id": data["id"],
                    "name": ev.subject,
                    "token": token,
                    "expected_content": token,
                    "path": f"graph/events/{data['id']}",
                }
                out.append(ent)
                self._events.append(ent)
                self.created_entities.append({"id": data["id"], "name": ev.subject})
        return out

    async def update_entities(self) -> List[Dict[str, Any]]:
        if not self._events:
            return []
        self.logger.info("🥁 Updating some events (subject tweak)")
        async with httpx.AsyncClient(base_url=GRAPH, timeout=30) as client:
            updated = []
            for ent in self._events[: min(3, len(self._events))]:
                await self._pace()
                r = await client.patch(
                    f"/me/events/{ent['id']}",
                    headers=self._hdrs(),
                    json={"subject": ent["name"] + " [updated]"},
                )
                r.raise_for_status()
                updated.append({**ent, "updated": True})
            return updated

    async def delete_entities(self) -> List[str]:
        return await self.delete_specific_entities(self._events)

    async def delete_specific_entities(self, entities: List[Dict[str, Any]]) -> List[str]:
        self.logger.info(f"🥁 Deleting {len(entities)} events")
        deleted: List[str] = []
        async with httpx.AsyncClient(base_url=GRAPH, timeout=30) as client:
            for ent in entities:
                try:
                    await self._pace()
                    r = await client.delete(f"/me/events/{ent['id']}", headers=self._hdrs())
                    if r.status_code in (204, 202):
                        deleted.append(ent["id"])
                    else:
                        self.logger.warning(
                            f"Delete event {ent['id']} -> {r.status_code}: {r.text}"
                        )
                except Exception as e:
                    self.logger.warning(f"Delete error for {ent['id']}: {e}")
        return deleted

    async def cleanup(self):
        """Comprehensive cleanup of all test calendar events."""
        self.logger.info("🧹 Starting comprehensive Outlook Calendar cleanup")

        cleanup_stats = {"events_deleted": 0, "errors": 0}

        try:
            # First, delete current session events
            if self._events:
                self.logger.info(f"🗑️ Cleaning up {len(self._events)} current session events")
                deleted = await self.delete_specific_entities(self._events)
                cleanup_stats["events_deleted"] += len(deleted)
                self._events.clear()

            # Search for any remaining monke test events by subject pattern
            # This catches any events that might have been created in previous failed runs
            await self._cleanup_orphaned_test_events(cleanup_stats)

            self.logger.info(
                f"🧹 Cleanup completed: {cleanup_stats['events_deleted']} events deleted, "
                f"{cleanup_stats['errors']} errors"
            )
        except Exception as e:
            self.logger.error(f"❌ Error during comprehensive cleanup: {e}")

    async def _cleanup_orphaned_test_events(self, stats: Dict[str, Any]):
        """Find and delete orphaned test events from previous runs."""
        try:
            async with httpx.AsyncClient(base_url=GRAPH, timeout=30) as client:
                # Search for events with monke test patterns in subject
                # Using OData filter to find test events
                filter_query = "startswith(subject, 'Test') or contains(subject, 'monke')"
                r = await client.get(
                    "/me/events",
                    headers=self._hdrs(),
                    params={"$filter": filter_query, "$top": 100},
                )

                if r.status_code == 200:
                    events = r.json().get("value", [])
                    test_events = [
                        e
                        for e in events
                        if any(
                            pattern in e.get("subject", "").lower()
                            for pattern in ["test", "monke", "demo", "sample"]
                        )
                    ]

                    if test_events:
                        self.logger.info(
                            f"🔍 Found {len(test_events)} potential test events to clean"
                        )
                        for event in test_events:
                            try:
                                await self._pace()
                                del_r = await client.delete(
                                    f"/me/events/{event['id']}", headers=self._hdrs()
                                )
                                if del_r.status_code in (204, 202):
                                    stats["events_deleted"] += 1
                                    self.logger.info(
                                        f"✅ Deleted orphaned event: {event.get('subject')}"
                                    )
                                else:
                                    stats["errors"] += 1
                            except Exception as e:
                                stats["errors"] += 1
                                self.logger.warning(f"⚠️ Failed to delete event {event['id']}: {e}")
        except Exception as e:
            self.logger.warning(f"⚠️ Could not search for orphaned events: {e}")

    def _hdrs(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

    async def _pace(self):
        now = time.time()
        if (delta := now - self._last_req) < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - delta)
        self._last_req = time.time()
