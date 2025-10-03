"""Box bongo implementation.

Creates, updates, and deletes test entities via the real Box API.
"""

import asyncio
import json
import time
import uuid
from typing import Any, Dict, List, Optional

import httpx
from monke.bongos.base_bongo import BaseBongo
from monke.utils.logging import get_logger


class BoxBongo(BaseBongo):
    """Bongo for Box that creates test entities for E2E testing.

    Key responsibilities:
    - Create test entities (folders, files, comments)
    - Embed verification tokens in content
    - Update entities to test incremental sync
    - Delete entities to test deletion detection
    - Clean up all test data
    """

    connector_type = "box"

    API_BASE = "https://api.box.com/2.0"
    UPLOAD_API = "https://upload.box.com/api/2.0"

    def __init__(self, credentials: Dict[str, Any], **kwargs):
        """Initialize the bongo.

        Args:
            credentials: Dict with "access_token"
            **kwargs: Configuration from test config file
        """
        super().__init__(credentials)
        self.access_token: str = credentials["access_token"]

        # Test configuration
        self.entity_count: int = int(kwargs.get("entity_count", 3))
        self.openai_model: str = kwargs.get("openai_model", "gpt-4.1-mini")
        self.max_concurrency: int = int(kwargs.get("max_concurrency", 2))

        # Runtime state - track ALL created entities
        self._test_folder_id: Optional[str] = None
        self._folders: List[Dict[str, Any]] = []
        self._files: List[Dict[str, Any]] = []
        self._comments: List[Dict[str, Any]] = []

        # Simple rate limiting
        self.last_request_time = 0.0
        self.min_delay = 0.3  # 300ms between requests

        self.logger = get_logger(f"{self.connector_type}_bongo")

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

    async def _ensure_test_folder(self, client: httpx.AsyncClient):
        """Ensure test folder exists in Box root."""
        if self._test_folder_id:
            return

        # Create a test folder in root (0)
        folder_name = f"Airweave_Test_{uuid.uuid4().hex[:8]}"

        await self._rate_limit()
        resp = await client.post(
            f"{self.API_BASE}/folders",
            headers=self._headers(),
            json={"name": folder_name, "parent": {"id": "0"}},
        )
        resp.raise_for_status()
        folder_data = resp.json()

        self._test_folder_id = folder_data["id"]
        self.logger.info(
            f"Created test folder: {folder_name} (ID: {self._test_folder_id})"
        )

    async def create_entities(self) -> List[Dict[str, Any]]:
        """Create ALL types of test entities.

        This is critical: Creates instances of EVERY entity type
        that the source connector syncs.

        Returns:
            List of entity descriptors with verification tokens
        """
        self.logger.info(f"🥁 Creating {self.entity_count} comprehensive test entities")

        from monke.generation.box import (
            generate_comment,
            generate_file,
            generate_folder,
        )

        all_entities: List[Dict[str, Any]] = []
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async with httpx.AsyncClient(timeout=60.0) as client:
            # Ensure we have a test folder
            await self._ensure_test_folder(client)

            # Create folder entities
            for i in range(self.entity_count):
                async with semaphore:
                    # Generate unique token for this folder
                    folder_token = str(uuid.uuid4())[:8]

                    self.logger.info(
                        f"Creating folder {i + 1}/{self.entity_count} with token {folder_token}"
                    )

                    # Generate content
                    folder_data = await generate_folder(self.openai_model, folder_token)

                    # Make folder name unique by appending token (Box doesn't allow duplicates)
                    unique_folder_name = f"{folder_data['name']}_{folder_token}"

                    # Put token prominently at start of description for reliable search
                    folder_description = (
                        f"Token: {folder_token}\n\n{folder_data['description']}"
                    )

                    # Create via API
                    await self._rate_limit()
                    resp = await client.post(
                        f"{self.API_BASE}/folders",
                        headers=self._headers(),
                        json={
                            "name": unique_folder_name,
                            "parent": {"id": self._test_folder_id},
                        },
                    )
                    resp.raise_for_status()
                    folder = resp.json()

                    # Box API doesn't support setting description during folder creation
                    # Update it separately
                    await self._rate_limit()
                    resp = await client.put(
                        f"{self.API_BASE}/folders/{folder['id']}",
                        headers=self._headers(),
                        json={"description": folder_description},
                    )
                    resp.raise_for_status()
                    folder = resp.json()  # Get updated folder with description

                    # Track the folder
                    folder_descriptor = {
                        "type": "folder",
                        "id": folder["id"],
                        "name": folder["name"],
                        "token": folder_token,
                        "expected_content": folder_token,
                        "path": f"box/folder/{folder['id']}",
                    }
                    self._folders.append(folder_descriptor)
                    all_entities.append(folder_descriptor)

                    # ========================================
                    # Create file entities in this folder
                    # ========================================

                    for file_idx in range(2):  # 2 files per folder
                        file_token = str(uuid.uuid4())[:8]

                        self.logger.info(
                            f"  Creating file {file_idx + 1}/2 in folder {folder['id']} "
                            f"with token {file_token}"
                        )

                        # Generate file content
                        file_content, filename, description = await generate_file(
                            self.openai_model, file_token
                        )

                        # Make filename unique by appending token (Box doesn't allow duplicates)
                        base_name = (
                            filename.rsplit(".", 1)[0] if "." in filename else filename
                        )
                        extension = (
                            filename.rsplit(".", 1)[1] if "." in filename else "txt"
                        )
                        unique_filename = f"{base_name}_{file_token}.{extension}"

                        # Upload the file
                        await self._rate_limit()

                        # Box upload API requires multipart/form-data with JSON attributes
                        files = {"file": (unique_filename, file_content, "text/plain")}
                        data = {
                            "attributes": json.dumps(
                                {
                                    "name": unique_filename,
                                    "parent": {"id": folder["id"]},
                                }
                            )
                        }

                        resp = await client.post(
                            f"{self.UPLOAD_API}/files/content",
                            headers={"Authorization": f"Bearer {self.access_token}"},
                            files=files,
                            data=data,
                        )
                        resp.raise_for_status()
                        upload_result = resp.json()

                        file_id = upload_result["entries"][0]["id"]

                        # Update file description
                        await self._rate_limit()
                        resp = await client.put(
                            f"{self.API_BASE}/files/{file_id}",
                            headers=self._headers(),
                            json={"description": description},
                        )
                        resp.raise_for_status()
                        file = resp.json()

                        # Track the file
                        file_descriptor = {
                            "type": "file",
                            "id": file["id"],
                            "name": file["name"],
                            "parent_id": folder["id"],
                            "token": file_token,
                            "expected_content": file_token,
                            "path": f"box/file/{file['id']}",
                        }
                        self._files.append(file_descriptor)
                        all_entities.append(file_descriptor)

                        # ========================================
                        # Create comment on this file
                        # ========================================

                        comment_token = str(uuid.uuid4())[:8]

                        self.logger.info(
                            f"    Creating comment on file {file['id']} "
                            f"with token {comment_token}"
                        )

                        comment_data = await generate_comment(
                            self.openai_model, comment_token
                        )

                        await self._rate_limit()
                        resp = await client.post(
                            f"{self.API_BASE}/comments",
                            headers=self._headers(),
                            json={
                                "item": {"type": "file", "id": file["id"]},
                                "message": comment_data["message"],
                            },
                        )
                        resp.raise_for_status()
                        comment = resp.json()

                        # Track the comment
                        comment_descriptor = {
                            "type": "comment",
                            "id": comment["id"],
                            "parent_id": file["id"],
                            "token": comment_token,
                            "expected_content": comment_token,
                            "path": f"box/comment/{comment['id']}",
                        }
                        self._comments.append(comment_descriptor)
                        all_entities.append(comment_descriptor)

        self.logger.info(
            f"✅ Created {len(self._folders)} folders, "
            f"{len(self._files)} files, "
            f"{len(self._comments)} comments"
        )

        self.created_entities = all_entities
        return all_entities

    async def update_entities(self) -> List[Dict[str, Any]]:
        """Update entities to test incremental sync.

        Strategy:
        - Update some folders
        - Update some files
        - Add new comments
        """
        self.logger.info("🥁 Updating test entities for incremental sync")

        if not self._folders:
            return []

        from monke.generation.box import generate_comment, generate_folder

        updated_entities: List[Dict[str, Any]] = []
        count = min(2, len(self._folders))  # Update first 2 folders

        async with httpx.AsyncClient(timeout=60.0) as client:
            # Update folders
            for i in range(count):
                folder = self._folders[i]

                # Generate new content with SAME token
                folder_data = await generate_folder(self.openai_model, folder["token"])

                await self._rate_limit()
                resp = await client.put(
                    f"{self.API_BASE}/folders/{folder['id']}",
                    headers=self._headers(),
                    json={
                        "name": folder_data["name"],
                        "description": folder_data["description"],
                    },
                )
                resp.raise_for_status()

                updated_entities.append({**folder, "name": folder_data["name"]})

            # Add new comments to existing files
            file_count = min(2, len(self._files))
            for i in range(file_count):
                file = self._files[i]
                comment_token = str(uuid.uuid4())[:8]

                comment_data = await generate_comment(self.openai_model, comment_token)

                await self._rate_limit()
                resp = await client.post(
                    f"{self.API_BASE}/comments",
                    headers=self._headers(),
                    json={
                        "item": {"type": "file", "id": file["id"]},
                        "message": comment_data["message"],
                    },
                )
                resp.raise_for_status()
                comment = resp.json()

                comment_descriptor = {
                    "type": "comment",
                    "id": comment["id"],
                    "parent_id": file["id"],
                    "token": comment_token,
                    "expected_content": comment_token,
                    "path": f"box/comment/{comment['id']}",
                }
                self._comments.append(comment_descriptor)
                updated_entities.append(comment_descriptor)

        return updated_entities

    async def delete_entities(self) -> List[str]:
        """Delete all created test entities."""
        self.logger.info("🥁 Deleting all Box test entities")
        deleted_ids = await self.delete_specific_entities(self.created_entities)
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
        deleted: List[str] = []

        async with httpx.AsyncClient(timeout=60.0) as client:
            # Delete in reverse order: comments, files, folders
            # First delete comments
            for entity in entities:
                if entity["type"] == "comment":
                    try:
                        await self._rate_limit()
                        resp = await client.delete(
                            f"{self.API_BASE}/comments/{entity['id']}",
                            headers=self._headers(),
                        )
                        if resp.status_code == 204:
                            deleted.append(entity["id"])
                    except Exception as e:
                        self.logger.warning(
                            f"Failed to delete comment {entity['id']}: {e}"
                        )

            # Then delete files
            for entity in entities:
                if entity["type"] == "file":
                    try:
                        await self._rate_limit()
                        resp = await client.delete(
                            f"{self.API_BASE}/files/{entity['id']}",
                            headers=self._headers(),
                        )
                        if resp.status_code == 204:
                            deleted.append(entity["id"])
                    except Exception as e:
                        self.logger.warning(
                            f"Failed to delete file {entity['id']}: {e}"
                        )

            # Finally delete folders (Box deletes contents automatically with recursive=true)
            # We need to track cascade-deleted children
            for entity in entities:
                if entity["type"] == "folder":
                    folder_id = entity["id"]

                    # Find all child entities that will be cascade-deleted
                    children_to_delete = []

                    # Find files in this folder
                    for file in self.created_entities:
                        if (
                            file["type"] == "file"
                            and file.get("parent_id") == folder_id
                        ):
                            file_id = file["id"]
                            children_to_delete.append(file_id)

                            # Find comments on this file (comments have parent_id = file_id)
                            for comment in self.created_entities:
                                if (
                                    comment["type"] == "comment"
                                    and comment.get("parent_id") == file_id
                                ):
                                    children_to_delete.append(comment["id"])

                    # Find nested folders
                    for subfolder in self.created_entities:
                        if (
                            subfolder["type"] == "folder"
                            and subfolder.get("parent_id") == folder_id
                        ):
                            children_to_delete.append(subfolder["id"])

                    try:
                        await self._rate_limit()
                        resp = await client.delete(
                            f"{self.API_BASE}/folders/{folder_id}?recursive=true",
                            headers=self._headers(),
                        )
                        if resp.status_code == 204:
                            # Add the folder itself
                            deleted.append(folder_id)
                            # Add all cascade-deleted children
                            deleted.extend(children_to_delete)
                            if children_to_delete:
                                self.logger.info(
                                    f"📎 Folder {folder_id} cascade-deleted {len(children_to_delete)} children"
                                )
                    except Exception as e:
                        self.logger.warning(f"Failed to delete folder {folder_id}: {e}")

        return deleted

    async def cleanup(self):
        """Comprehensive cleanup of ALL test data."""
        self.logger.info("🧹 Starting comprehensive Box cleanup")

        cleanup_stats = {
            "comments_deleted": 0,
            "files_deleted": 0,
            "folders_deleted": 0,
            "errors": 0,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                # 1. Clean up current session
                # Delete comments
                for comment in self._comments:
                    try:
                        await self._rate_limit()
                        resp = await client.delete(
                            f"{self.API_BASE}/comments/{comment['id']}",
                            headers=self._headers(),
                        )
                        if resp.status_code == 204:
                            cleanup_stats["comments_deleted"] += 1
                    except Exception as e:
                        self.logger.warning(
                            f"Failed to delete comment {comment['id']}: {e}"
                        )
                        cleanup_stats["errors"] += 1

                # Delete files
                for file in self._files:
                    try:
                        await self._rate_limit()
                        resp = await client.delete(
                            f"{self.API_BASE}/files/{file['id']}",
                            headers=self._headers(),
                        )
                        if resp.status_code == 204:
                            cleanup_stats["files_deleted"] += 1
                    except Exception as e:
                        self.logger.warning(f"Failed to delete file {file['id']}: {e}")
                        cleanup_stats["errors"] += 1

                # Delete folders
                for folder in self._folders:
                    try:
                        await self._rate_limit()
                        resp = await client.delete(
                            f"{self.API_BASE}/folders/{folder['id']}?recursive=true",
                            headers=self._headers(),
                        )
                        if resp.status_code == 204:
                            cleanup_stats["folders_deleted"] += 1
                    except Exception as e:
                        self.logger.warning(
                            f"Failed to delete folder {folder['id']}: {e}"
                        )
                        cleanup_stats["errors"] += 1

                # Delete test folder if it exists
                if self._test_folder_id:
                    try:
                        await self._rate_limit()
                        resp = await client.delete(
                            f"{self.API_BASE}/folders/{self._test_folder_id}?recursive=true",
                            headers=self._headers(),
                        )
                        if resp.status_code == 204:
                            cleanup_stats["folders_deleted"] += 1
                    except Exception as e:
                        self.logger.warning(f"Failed to delete test folder: {e}")
                        cleanup_stats["errors"] += 1

                # 2. Find and clean up orphaned test folders
                try:
                    await self._rate_limit()
                    resp = await client.get(
                        f"{self.API_BASE}/folders/0/items", headers=self._headers()
                    )
                    if resp.status_code == 200:
                        items = resp.json().get("entries", [])
                        for item in items:
                            if item.get("type") == "folder" and item.get(
                                "name", ""
                            ).startswith("Airweave_Test_"):
                                try:
                                    await self._rate_limit()
                                    resp = await client.delete(
                                        f"{self.API_BASE}/folders/{item['id']}?recursive=true",
                                        headers=self._headers(),
                                    )
                                    if resp.status_code == 204:
                                        cleanup_stats["folders_deleted"] += 1
                                        self.logger.info(
                                            f"Cleaned up orphaned folder: {item['name']}"
                                        )
                                except Exception:
                                    cleanup_stats["errors"] += 1
                except Exception as e:
                    self.logger.warning(f"Failed to clean up orphaned folders: {e}")

                self.logger.info(
                    f"🧹 Cleanup completed: "
                    f"{cleanup_stats['comments_deleted']} comments, "
                    f"{cleanup_stats['files_deleted']} files, "
                    f"{cleanup_stats['folders_deleted']} folders deleted, "
                    f"{cleanup_stats['errors']} errors"
                )

            except Exception as e:
                self.logger.error(f"❌ Error during cleanup: {e}")
                # Don't re-raise - cleanup is best-effort
