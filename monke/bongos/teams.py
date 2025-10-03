"""Microsoft Teams bongo implementation.

Creates, updates, and deletes test channels and messages via the Microsoft Graph API.
"""

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional

import httpx
from monke.bongos.base_bongo import BaseBongo
from monke.utils.logging import get_logger


class TeamsBongo(BaseBongo):
    """Bongo for Microsoft Teams that creates test entities for E2E testing.

    Key responsibilities:
    - Create test channels and messages in an existing team
    - Embed verification tokens in message content
    - Update messages to test incremental sync
    - Delete entities to test deletion detection
    - Clean up all test data

    Note: Creating new teams requires admin permissions, so we use an existing team
    that the authenticated user has access to.
    """

    connector_type = "teams"

    GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

    def __init__(self, credentials: Dict[str, Any], **kwargs):
        """Initialize the Teams bongo.

        Args:
            credentials: Dict with "access_token" for Microsoft Graph
            **kwargs: Configuration from test config file
        """
        super().__init__(credentials)
        self.access_token: str = credentials["access_token"]

        # Test configuration
        self.entity_count: int = int(kwargs.get("entity_count", 3))
        self.openai_model: str = kwargs.get("openai_model", "gpt-4.1-mini")
        self.max_concurrency: int = int(kwargs.get("max_concurrency", 2))

        # Simple rate limiting
        self.last_request_time = 0.0
        self.min_delay = 0.5  # 500ms between requests

        # Runtime state - track ALL created entities
        self._team_id: Optional[str] = None
        self._team_name: Optional[str] = None
        self._channels: List[Dict[str, Any]] = []
        self._messages: List[Dict[str, Any]] = []
        self._chat_id: Optional[str] = None
        self._chat_messages: List[Dict[str, Any]] = []

        self.logger = get_logger(f"{self.connector_type}_bongo")

    async def create_entities(self) -> List[Dict[str, Any]]:
        """Create ALL types of test entities.

        Creates:
        - Test channel in an existing team
        - Channel messages with verification tokens
        - Group chat
        - Chat messages with verification tokens

        Returns:
            List of entity descriptors with verification tokens
        """
        self.logger.info(f"🥁 Creating {self.entity_count} test entities")

        # Ensure we have a team to work with
        await self._ensure_team()

        from monke.generation.teams import (
            generate_teams_channel,
            generate_teams_message,
        )

        all_entities: List[Dict[str, Any]] = []
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async with httpx.AsyncClient() as client:
            # Create a test channel
            self.logger.info("Creating test channel...")
            channel_data = await generate_teams_channel(self.openai_model)

            await self._rate_limit()
            channel_name = f"monke-test-{str(uuid.uuid4())[:6]}-{channel_data['display_name'][:20]}"

            try:
                resp = await client.post(
                    f"{self.GRAPH_BASE_URL}/teams/{self._team_id}/channels",
                    headers=self._headers(),
                    json={
                        "displayName": channel_name,
                        "description": channel_data["description"],
                        "membershipType": "standard",
                    },
                )
                resp.raise_for_status()
                channel = resp.json()
                channel_id = channel["id"]

                channel_descriptor = {
                    "type": "channel",
                    "id": channel_id,
                    "name": channel_name,
                    "team_id": self._team_id,
                }
                self._channels.append(channel_descriptor)
                # Don't add channel to all_entities - it has no token to verify

                self.logger.info(f"✅ Created test channel: {channel_name}")

                # Wait for channel to be ready
                await asyncio.sleep(2)

                # Create messages in the channel
                async def create_channel_message(idx: int):
                    async with semaphore:
                        message_token = str(uuid.uuid4())[:8]

                        self.logger.info(
                            f"Creating channel message {idx + 1}/{self.entity_count} "
                            f"with token {message_token}"
                        )

                        message_data = await generate_teams_message(
                            self.openai_model, message_token
                        )

                        await self._rate_limit()
                        resp = await client.post(
                            f"{self.GRAPH_BASE_URL}/teams/{self._team_id}/channels/{channel_id}/messages",
                            headers=self._headers(),
                            json={
                                "subject": message_data.get("subject"),
                                "body": {
                                    "contentType": "html",
                                    "content": message_data["body"],
                                },
                            },
                        )
                        resp.raise_for_status()
                        message = resp.json()

                        message_descriptor = {
                            "type": "channel_message",
                            "id": message["id"],
                            "channel_id": channel_id,
                            "team_id": self._team_id,
                            "token": message_token,
                            "expected_content": message_token,
                            "path": f"teams/channel_message/{message['id']}",
                        }
                        return message_descriptor

                # Create channel messages in parallel
                message_tasks = [
                    create_channel_message(i) for i in range(self.entity_count)
                ]
                message_results = await asyncio.gather(
                    *message_tasks, return_exceptions=True
                )

                for result in message_results:
                    if isinstance(result, Exception):
                        self.logger.error(f"Failed to create channel message: {result}")
                    elif result:
                        self._messages.append(result)
                        all_entities.append(result)
                        self.logger.info(
                            f"✅ Created channel message with token {result['token']}"
                        )

            except Exception as e:
                self.logger.error(f"Error creating test channel: {e}")
                # Continue with chat creation even if channel fails

            # Create a group chat (optional - might fail due to permissions)
            try:
                self.logger.info("Creating test group chat...")

                # Get current user ID
                await self._rate_limit()
                me_resp = await client.get(
                    f"{self.GRAPH_BASE_URL}/me",
                    headers=self._headers(),
                )
                me_resp.raise_for_status()
                my_user_id = me_resp.json()["id"]

                # Create a group chat (requires at least 2 members)
                # Note: In a real scenario, we'd need another user. For testing,
                # we'll try to create with just ourselves, which might fail.
                # This is a limitation of the Graph API.
                await self._rate_limit()
                chat_resp = await client.post(
                    f"{self.GRAPH_BASE_URL}/chats",
                    headers=self._headers(),
                    json={
                        "chatType": "group",
                        "topic": f"Monke Test Chat {str(uuid.uuid4())[:6]}",
                        "members": [
                            {
                                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                                "roles": ["owner"],
                                "user@odata.bind": f"{self.GRAPH_BASE_URL}/users('{my_user_id}')",
                            }
                        ],
                    },
                )

                if chat_resp.status_code in (200, 201):
                    chat = chat_resp.json()
                    self._chat_id = chat["id"]
                    self.logger.info(f"✅ Created test group chat: {self._chat_id}")

                    # Wait for chat to be ready
                    await asyncio.sleep(2)

                    # Create messages in the chat
                    for i in range(min(2, self.entity_count)):
                        message_token = str(uuid.uuid4())[:8]

                        self.logger.info(
                            f"Creating chat message {i + 1} with token {message_token}"
                        )

                        message_data = await generate_teams_message(
                            self.openai_model, message_token
                        )

                        await self._rate_limit()
                        resp = await client.post(
                            f"{self.GRAPH_BASE_URL}/chats/{self._chat_id}/messages",
                            headers=self._headers(),
                            json={
                                "body": {
                                    "contentType": "html",
                                    "content": message_data["body"],
                                },
                            },
                        )
                        resp.raise_for_status()
                        message = resp.json()

                        message_descriptor = {
                            "type": "chat_message",
                            "id": message["id"],
                            "chat_id": self._chat_id,
                            "token": message_token,
                            "expected_content": message_token,
                            "path": f"teams/chat_message/{message['id']}",
                        }
                        self._chat_messages.append(message_descriptor)
                        all_entities.append(message_descriptor)
                        self.logger.info(
                            f"✅ Created chat message with token {message_token}"
                        )

                else:
                    self.logger.warning(
                        f"Could not create group chat: {chat_resp.status_code} - {chat_resp.text}"
                    )

            except Exception as e:
                self.logger.warning(f"Error creating test chat: {e}")
                # Chat creation might fail due to permissions - that's ok

        self.logger.info(
            f"✅ Created {len(self._channels)} channels, "
            f"{len(self._messages)} channel messages, "
            f"{len(self._chat_messages)} chat messages"
        )

        self.created_entities = all_entities
        return all_entities

    async def update_entities(self) -> List[Dict[str, Any]]:
        """Update entities to test incremental sync.

        Note: Microsoft Graph doesn't support updating messages directly.
        Instead, we'll create new messages with the same tokens.

        Returns:
            List of updated entity descriptors
        """
        self.logger.info("🥁 Creating new messages for incremental sync test")

        if not self._channels:
            return []

        from monke.generation.teams import generate_teams_message

        updated_entities: List[Dict[str, Any]] = []
        channel = self._channels[0]

        async with httpx.AsyncClient() as client:
            # Create 1-2 new messages in the test channel
            for i in range(min(2, self.entity_count)):
                message_token = str(uuid.uuid4())[:8]

                self.logger.info(
                    f"Creating new message {i + 1} with token {message_token}"
                )

                message_data = await generate_teams_message(
                    self.openai_model, message_token
                )

                await self._rate_limit()
                resp = await client.post(
                    f"{self.GRAPH_BASE_URL}/teams/{channel['team_id']}/channels/{channel['id']}/messages",
                    headers=self._headers(),
                    json={
                        "subject": message_data.get("subject"),
                        "body": {
                            "contentType": "html",
                            "content": message_data["body"],
                        },
                    },
                )
                resp.raise_for_status()
                message = resp.json()

                message_descriptor = {
                    "type": "channel_message",
                    "id": message["id"],
                    "channel_id": channel["id"],
                    "team_id": channel["team_id"],
                    "token": message_token,
                    "expected_content": message_token,
                    "path": f"teams/channel_message/{message['id']}",
                }
                self._messages.append(message_descriptor)
                updated_entities.append(message_descriptor)

        return updated_entities

    async def delete_entities(self) -> List[str]:
        """Delete all created test entities.

        Returns:
            List of deleted entity IDs
        """
        self.logger.info("🥁 Deleting all test entities")
        deleted_ids = []

        async with httpx.AsyncClient() as client:
            # Delete messages (note: message deletion might not be supported)
            for message in self._messages + self._chat_messages:
                try:
                    await self._rate_limit()
                    # Note: Message deletion in Graph API requires specific permissions
                    # and might not work in all scenarios
                    if message.get("channel_id"):
                        url = (
                            f"{self.GRAPH_BASE_URL}/teams/{message['team_id']}/channels/"
                            f"{message['channel_id']}/messages/{message['id']}/softDelete"
                        )
                    else:
                        url = f"{self.GRAPH_BASE_URL}/chats/{message['chat_id']}/messages/{message['id']}/softDelete"

                    resp = await client.post(url, headers=self._headers())

                    if resp.status_code in (200, 204):
                        deleted_ids.append(message["id"])
                    else:
                        self.logger.debug(
                            f"Could not delete message {message['id']}: {resp.status_code}"
                        )
                except Exception as e:
                    self.logger.debug(
                        f"Error deleting message {message.get('id')}: {e}"
                    )

            # Delete channels
            for channel in self._channels:
                try:
                    await self._rate_limit()
                    resp = await client.delete(
                        f"{self.GRAPH_BASE_URL}/teams/{channel['team_id']}/channels/{channel['id']}",
                        headers=self._headers(),
                    )
                    if resp.status_code in (200, 204):
                        deleted_ids.append(channel["id"])
                        self.logger.info(f"Deleted channel: {channel['name']}")
                    else:
                        self.logger.warning(
                            f"Could not delete channel {channel['id']}: {resp.status_code}"
                        )
                except Exception as e:
                    self.logger.warning(
                        f"Error deleting channel {channel.get('id')}: {e}"
                    )

        return deleted_ids

    async def delete_specific_entities(
        self, entities: List[Dict[str, Any]]
    ) -> List[str]:
        """Delete specific entities by ID.

        Args:
            entities: List of entity descriptors to delete

        Returns:
            List of successfully deleted entity IDs
        """
        self.logger.info(f"🥁 Deleting {len(entities)} specific entities")
        deleted_ids = []

        async with httpx.AsyncClient() as client:
            for entity in entities:
                try:
                    entity_type = entity.get("type")
                    entity_id = entity.get("id")

                    await self._rate_limit()

                    if entity_type == "channel_message":
                        url = (
                            f"{self.GRAPH_BASE_URL}/teams/{entity['team_id']}/channels/"
                            f"{entity['channel_id']}/messages/{entity_id}/softDelete"
                        )
                        resp = await client.post(url, headers=self._headers())
                    elif entity_type == "chat_message":
                        url = f"{self.GRAPH_BASE_URL}/chats/{entity['chat_id']}/messages/{entity_id}/softDelete"
                        resp = await client.post(url, headers=self._headers())
                    elif entity_type == "channel":
                        url = f"{self.GRAPH_BASE_URL}/teams/{entity['team_id']}/channels/{entity_id}"
                        resp = await client.delete(url, headers=self._headers())
                    else:
                        continue

                    if resp.status_code in (200, 204):
                        deleted_ids.append(entity_id)
                    else:
                        self.logger.debug(
                            f"Could not delete {entity_type} {entity_id}: {resp.status_code}"
                        )

                except Exception as e:
                    self.logger.warning(
                        f"Error deleting {entity.get('type')} {entity.get('id')}: {e}"
                    )

        return deleted_ids

    async def cleanup(self):
        """Comprehensive cleanup of ALL test data.

        This should:
        1. Delete current session entities
        2. Find orphaned test channels from failed runs
        3. Delete test channels
        """
        self.logger.info("🧹 Starting comprehensive workspace cleanup")

        if not self._team_id:
            await self._ensure_team()

        cleanup_stats = {
            "messages_deleted": 0,
            "channels_deleted": 0,
            "errors": 0,
        }

        try:
            async with httpx.AsyncClient() as client:
                # 1. Clean up current session
                for message in self._messages + self._chat_messages:
                    try:
                        # Attempt soft delete
                        await self._rate_limit()
                        if message.get("channel_id"):
                            url = (
                                f"{self.GRAPH_BASE_URL}/teams/{message['team_id']}/channels/"
                                f"{message['channel_id']}/messages/{message['id']}/softDelete"
                            )
                        else:
                            url = f"{self.GRAPH_BASE_URL}/chats/{message['chat_id']}/messages/{message['id']}/softDelete"

                        resp = await client.post(url, headers=self._headers())
                        if resp.status_code in (200, 204):
                            cleanup_stats["messages_deleted"] += 1
                    except Exception as e:
                        self.logger.debug(f"Failed to delete message: {e}")
                        cleanup_stats["errors"] += 1

                for channel in self._channels:
                    try:
                        await self._rate_limit()
                        resp = await client.delete(
                            f"{self.GRAPH_BASE_URL}/teams/{channel['team_id']}/channels/{channel['id']}",
                            headers=self._headers(),
                        )
                        if resp.status_code in (200, 204):
                            cleanup_stats["channels_deleted"] += 1
                    except Exception as e:
                        self.logger.debug(f"Failed to delete channel: {e}")
                        cleanup_stats["errors"] += 1

                # 2. Find and clean up orphaned test channels
                orphaned_channels = await self._find_test_channels(client)
                for channel in orphaned_channels:
                    try:
                        await self._rate_limit()
                        resp = await client.delete(
                            f"{self.GRAPH_BASE_URL}/teams/{self._team_id}/channels/{channel['id']}",
                            headers=self._headers(),
                        )
                        if resp.status_code in (200, 204):
                            cleanup_stats["channels_deleted"] += 1
                    except Exception as e:
                        self.logger.debug(f"Failed to delete orphaned channel: {e}")
                        cleanup_stats["errors"] += 1

            self.logger.info(
                f"🧹 Cleanup completed: {cleanup_stats['messages_deleted']} messages, "
                f"{cleanup_stats['channels_deleted']} channels deleted, "
                f"{cleanup_stats['errors']} errors"
            )

        except Exception as e:
            self.logger.error(f"❌ Error during cleanup: {e}")
            # Don't re-raise - cleanup is best-effort

    async def _ensure_team(self):
        """Ensure we have a team to work with."""
        if self._team_id:
            return

        async with httpx.AsyncClient() as client:
            await self._rate_limit()
            resp = await client.get(
                f"{self.GRAPH_BASE_URL}/me/joinedTeams",
                headers=self._headers(),
            )
            resp.raise_for_status()
            teams = resp.json().get("value", [])

            if not teams:
                raise RuntimeError(
                    "No Teams accessible. Please ensure the user is a member of at least one team."
                )

            # Use the first team
            self._team_id = teams[0]["id"]
            self._team_name = teams[0].get("displayName", "Unknown Team")
            self.logger.info(f"Using team: {self._team_name} ({self._team_id})")

    async def _find_test_channels(
        self, client: httpx.AsyncClient
    ) -> List[Dict[str, Any]]:
        """Find orphaned monke test channels in the team."""
        test_channels = []

        try:
            await self._rate_limit()
            resp = await client.get(
                f"{self.GRAPH_BASE_URL}/teams/{self._team_id}/channels",
                headers=self._headers(),
            )
            resp.raise_for_status()

            channels = resp.json().get("value", [])
            for channel in channels:
                name = channel.get("displayName", "")
                if name.startswith("monke-test-") or "monke" in name.lower():
                    test_channels.append(channel)

        except Exception as e:
            self.logger.warning(f"Error finding test channels: {e}")

        return test_channels

    def _headers(self) -> Dict[str, str]:
        """Return auth headers for API requests."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _rate_limit(self):
        """Simple rate limiting."""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.min_delay:
            await asyncio.sleep(self.min_delay - elapsed)
        self.last_request_time = time.time()
