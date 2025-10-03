"""ClickUp bongo implementation.

Creates, updates, and deletes test entities via the real ClickUp API.
"""

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional

import httpx
from monke.bongos.base_bongo import BaseBongo
from monke.utils.logging import get_logger


class ClickUpBongo(BaseBongo):
    """Bongo for ClickUp that creates comprehensive test entities for E2E testing.

    Creates test entities in ClickUp including tasks, subtasks, comments, and file attachments.
    Uses a test space and list to keep everything organized and easy to clean up.
    """

    connector_type = "clickup"

    API_BASE = "https://api.clickup.com/api/v2"

    def __init__(self, credentials: Dict[str, Any], **kwargs):
        """Initialize the ClickUp bongo.

        Args:
            credentials: Dict with at least "access_token" (ClickUp OAuth token)
            **kwargs: Configuration from config file
        """
        super().__init__(credentials)
        self.access_token: str = credentials["access_token"]
        self.entity_count: int = int(kwargs.get("entity_count", 3))
        self.openai_model: str = kwargs.get("openai_model", "gpt-4.1-mini")
        self.max_concurrency: int = int(kwargs.get("max_concurrency", 3))
        # Use rate_limit_delay_ms from config if provided, otherwise default to 500ms
        rate_limit_ms = int(kwargs.get("rate_limit_delay_ms", 500))
        self.rate_limit_delay: float = rate_limit_ms / 1000.0

        # Runtime state - track ALL created entities
        self._workspace_id: Optional[str] = None
        self._space_id: Optional[str] = None
        self._list_id: Optional[str] = None
        self._tasks: List[Dict[str, Any]] = []
        self._subtasks: List[Dict[str, Any]] = []
        self._comments: List[Dict[str, Any]] = []
        self._files: List[Dict[str, Any]] = []

        # Pacing
        self.last_request_time = 0.0

        self.logger = get_logger("clickup_bongo")

    async def create_entities(self) -> List[Dict[str, Any]]:
        """Create comprehensive test entities in ClickUp.

        Creates:
        - Tasks (main entities)
        - Subtasks (nested under tasks)
        - Comments (on tasks and subtasks)
        - File attachments (on tasks)

        Returns:
            List of entity descriptors with verification tokens
        """
        self.logger.info(f"🥁 Creating {self.entity_count} comprehensive ClickUp entities")

        # Ensure prerequisites
        await self._ensure_workspace()
        await self._ensure_space()
        await self._ensure_list()

        from monke.generation.clickup import (
            generate_clickup_task,
            generate_clickup_subtask,
            generate_clickup_comment,
            generate_clickup_file,
        )

        all_entities: List[Dict[str, Any]] = []
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Create parent entities (tasks)
            for i in range(self.entity_count):
                async with semaphore:
                    try:
                        # Generate unique token for this task
                        task_token = str(uuid.uuid4())[:8]

                        self.logger.info(
                            f"Creating task {i+1}/{self.entity_count} with token {task_token}"
                        )

                        # Generate content
                        task_name, task_description = await generate_clickup_task(
                            self.openai_model, task_token
                        )

                        # Create task via API
                        await self._rate_limit()
                        resp = await client.post(
                            f"{self.API_BASE}/list/{self._list_id}/task",
                            headers=self._headers(),
                            json={
                                "name": task_name,
                                "description": task_description,
                                "status": "to do",
                            },
                        )
                        resp.raise_for_status()
                        task = resp.json()

                        # Track the task
                        task_descriptor = {
                            "type": "task",
                            "id": task["id"],
                            "name": task_name,
                            "token": task_token,
                            "expected_content": task_token,
                            "path": f"clickup/task/{task['id']}",
                        }
                        self._tasks.append(task_descriptor)
                        all_entities.append(task_descriptor)

                        self.logger.info(f"✅ Created task: {task_name[:50]}...")

                        # ========================================
                        # CRITICAL: Create child entities
                        # ========================================

                        # 1. Create subtasks for this task (1-2 subtasks)
                        subtask_count = 2
                        for subtask_idx in range(subtask_count):
                            try:
                                subtask_token = str(uuid.uuid4())[:8]

                                self.logger.info(
                                    f"  Creating subtask {subtask_idx+1}/{subtask_count} "
                                    f"for task {task['id']} with token {subtask_token}"
                                )

                                subtask_name, subtask_description = await generate_clickup_subtask(
                                    self.openai_model, subtask_token, task_name
                                )

                                await self._rate_limit()
                                resp = await client.post(
                                    f"{self.API_BASE}/list/{self._list_id}/task",
                                    headers=self._headers(),
                                    json={
                                        "name": subtask_name,
                                        "description": subtask_description,
                                        "parent": task["id"],  # This makes it a subtask
                                    },
                                )
                                resp.raise_for_status()
                                subtask = resp.json()

                                # Track the subtask
                                subtask_descriptor = {
                                    "type": "subtask",
                                    "id": subtask["id"],
                                    "parent_id": task["id"],
                                    "name": subtask_name,
                                    "token": subtask_token,
                                    "expected_content": subtask_token,
                                    "path": f"clickup/subtask/{subtask['id']}",
                                }
                                self._subtasks.append(subtask_descriptor)
                                all_entities.append(subtask_descriptor)

                                self.logger.info(f"  ✅ Created subtask: {subtask_name[:40]}...")

                            except Exception as e:
                                self.logger.warning(
                                    f"Failed to create subtask {subtask_idx+1} for task {task['id']}: {e}"
                                )

                        # 2. Create comments for this task (2 comments)
                        comment_count = 2
                        for comment_idx in range(comment_count):
                            try:
                                comment_token = str(uuid.uuid4())[:8]

                                self.logger.info(
                                    f"  Creating comment {comment_idx+1}/{comment_count} "
                                    f"for task {task['id']} with token {comment_token}"
                                )

                                comment_text = await generate_clickup_comment(
                                    self.openai_model, comment_token
                                )

                                await self._rate_limit()
                                resp = await client.post(
                                    f"{self.API_BASE}/task/{task['id']}/comment",
                                    headers=self._headers(),
                                    json={
                                        "comment_text": comment_text,
                                    },
                                )
                                resp.raise_for_status()
                                comment = resp.json()

                                # Track the comment
                                comment_descriptor = {
                                    "type": "comment",
                                    "id": comment["id"],
                                    "parent_id": task["id"],
                                    "token": comment_token,
                                    "expected_content": comment_token,
                                    "path": f"clickup/comment/{comment['id']}",
                                }
                                self._comments.append(comment_descriptor)
                                all_entities.append(comment_descriptor)

                                self.logger.info(f"  ✅ Created comment with token {comment_token}")

                            except Exception as e:
                                self.logger.warning(
                                    f"Failed to create comment {comment_idx+1} for task {task['id']}: {e}"
                                )

                        # 3. Create file attachment for this task (1 file)
                        try:
                            file_token = str(uuid.uuid4())[:8]

                            self.logger.info(
                                f"  Creating file attachment for task {task['id']} "
                                f"with token {file_token}"
                            )

                            # Generate a test file
                            file_name, file_content = await generate_clickup_file(
                                self.openai_model, file_token
                            )

                            await self._rate_limit()

                            # Upload the file
                            files = {
                                "attachment": (
                                    file_name,
                                    file_content.encode("utf-8"),
                                    "text/plain",
                                )
                            }
                            resp = await client.post(
                                f"{self.API_BASE}/task/{task['id']}/attachment",
                                headers={"Authorization": f"Bearer {self.access_token}"},
                                files=files,
                            )
                            resp.raise_for_status()
                            attachment = resp.json()

                            # Track the file
                            file_descriptor = {
                                "type": "file",
                                "id": attachment["id"],
                                "parent_id": task["id"],
                                "name": file_name,
                                "token": file_token,
                                "expected_content": file_token,
                                "path": f"clickup/file/{attachment['id']}",
                            }
                            self._files.append(file_descriptor)
                            all_entities.append(file_descriptor)

                            self.logger.info(f"  ✅ Created file: {file_name}")

                        except Exception as e:
                            self.logger.warning(
                                f"Failed to create file attachment for task {task['id']}: {e}"
                            )

                    except Exception as e:
                        self.logger.error(f"Failed to create task {i+1}: {e}")
                        # Continue with next task

        self.logger.info(
            f"✅ Created {len(self._tasks)} tasks, "
            f"{len(self._subtasks)} subtasks, "
            f"{len(self._comments)} comments, "
            f"{len(self._files)} files"
        )

        self.created_entities = all_entities
        return all_entities

    async def update_entities(self) -> List[Dict[str, Any]]:
        """Update entities to test incremental sync.

        Strategy:
        - Update a subset of tasks
        - Add new comments to updated tasks
        """
        self.logger.info("🥁 Updating test entities for incremental sync")

        if not self._tasks:
            return []

        from monke.generation.clickup import generate_clickup_task, generate_clickup_comment

        updated_entities: List[Dict[str, Any]] = []
        count = min(2, len(self._tasks))  # Update first 2 tasks

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Update tasks
            for i in range(count):
                task = self._tasks[i]

                try:
                    # Generate new content with SAME token
                    task_name, task_description = await generate_clickup_task(
                        self.openai_model, task["token"]
                    )

                    await self._rate_limit()
                    resp = await client.put(
                        f"{self.API_BASE}/task/{task['id']}",
                        headers=self._headers(),
                        json={
                            "name": task_name,
                            "description": task_description,
                        },
                    )
                    resp.raise_for_status()

                    updated_entities.append(
                        {
                            **task,
                            "name": task_name,
                        }
                    )

                    self.logger.info(f"✅ Updated task: {task_name[:50]}...")

                    # Add a new comment to the updated task
                    try:
                        comment_token = str(uuid.uuid4())[:8]

                        comment_text = await generate_clickup_comment(
                            self.openai_model, comment_token
                        )

                        await self._rate_limit()
                        resp = await client.post(
                            f"{self.API_BASE}/task/{task['id']}/comment",
                            headers=self._headers(),
                            json={
                                "comment_text": comment_text,
                            },
                        )
                        resp.raise_for_status()
                        comment = resp.json()

                        comment_descriptor = {
                            "type": "comment",
                            "id": comment["id"],
                            "parent_id": task["id"],
                            "token": comment_token,
                            "expected_content": comment_token,
                            "path": f"clickup/comment/{comment['id']}",
                        }
                        self._comments.append(comment_descriptor)
                        updated_entities.append(comment_descriptor)

                        self.logger.info(f"  ✅ Added new comment with token {comment_token}")

                    except Exception as e:
                        self.logger.warning(
                            f"Failed to add comment to updated task {task['id']}: {e}"
                        )

                except Exception as e:
                    self.logger.error(f"Failed to update task {task['id']}: {e}")

        return updated_entities

    async def delete_entities(self) -> List[str]:
        """Delete all created test entities.

        Returns:
            List of deleted entity IDs
        """
        return await self.delete_specific_entities(self.created_entities)

    async def delete_specific_entities(self, entities: List[Dict[str, Any]]) -> List[str]:
        """Delete specific entities by ID.

        Args:
            entities: List of entity descriptors to delete

        Returns:
            List of successfully deleted entity IDs (including cascade-deleted children)
        """
        self.logger.info(f"🗑️  Deleting {len(entities)} specific entities")

        deleted_ids: List[str] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Group entities by type for proper deletion order
            # Order: files → comments → subtasks → tasks
            files_to_delete = [e for e in entities if e["type"] == "file"]
            comments_to_delete = [e for e in entities if e["type"] == "comment"]
            subtasks_to_delete = [e for e in entities if e["type"] == "subtask"]
            tasks_to_delete = [e for e in entities if e["type"] == "task"]

            # IMPORTANT: When deleting tasks, ClickUp cascades deletion to all children
            # Track which child entities will be automatically deleted
            cascade_deleted_children: List[str] = []
            for task in tasks_to_delete:
                task_id = task["id"]
                # Find all children of this task
                for entity in self.created_entities:
                    if entity.get("parent_id") == task_id:
                        cascade_deleted_children.append(entity["id"])
                        self.logger.info(
                            f"  📎 Task {task_id} deletion will cascade to {entity['type']} {entity['id']}"
                        )

            # Delete files first (skip those that will be cascade-deleted)
            for file in files_to_delete:
                if file["id"] in cascade_deleted_children:
                    self.logger.info(
                        f"  ⏭️  Skipping file {file['id']} (will be cascade-deleted with parent task)"
                    )
                    continue
                try:
                    await self._rate_limit()
                    # ClickUp doesn't have a direct file delete endpoint in v2
                    # Files are deleted when their parent task is deleted
                    self.logger.info(f"  Skipping file {file['id']} (will be deleted with task)")
                except Exception as e:
                    self.logger.warning(f"Error handling file {file['id']}: {e}")

            # Delete comments (skip those that will be cascade-deleted)
            for comment in comments_to_delete:
                if comment["id"] in cascade_deleted_children:
                    self.logger.info(
                        f"  ⏭️  Skipping comment {comment['id']} (will be cascade-deleted with parent task)"
                    )
                    continue
                try:
                    await self._rate_limit()
                    resp = await client.delete(
                        f"{self.API_BASE}/comment/{comment['id']}",
                        headers=self._headers(),
                    )
                    if resp.status_code in (200, 204):
                        deleted_ids.append(comment["id"])
                        self.logger.info(f"  ✅ Deleted comment {comment['id']}")
                    else:
                        self.logger.warning(
                            f"Failed to delete comment {comment['id']}: {resp.status_code}"
                        )
                except Exception as e:
                    self.logger.warning(f"Failed to delete comment {comment['id']}: {e}")

            # Delete subtasks (skip those that will be cascade-deleted)
            for subtask in subtasks_to_delete:
                if subtask["id"] in cascade_deleted_children:
                    self.logger.info(
                        f"  ⏭️  Skipping subtask {subtask['id']} (will be cascade-deleted with parent task)"
                    )
                    continue
                try:
                    await self._rate_limit()
                    resp = await client.delete(
                        f"{self.API_BASE}/task/{subtask['id']}",
                        headers=self._headers(),
                    )
                    if resp.status_code in (200, 204):
                        deleted_ids.append(subtask["id"])
                        self.logger.info(f"  ✅ Deleted subtask {subtask['id']}")
                    else:
                        self.logger.warning(
                            f"Failed to delete subtask {subtask['id']}: {resp.status_code}"
                        )
                except Exception as e:
                    self.logger.warning(f"Failed to delete subtask {subtask['id']}: {e}")

            # Delete tasks (and track cascaded children)
            for task in tasks_to_delete:
                try:
                    await self._rate_limit()
                    resp = await client.delete(
                        f"{self.API_BASE}/task/{task['id']}",
                        headers=self._headers(),
                    )
                    if resp.status_code in (200, 204):
                        deleted_ids.append(task["id"])
                        self.logger.info(f"  ✅ Deleted task {task['id']}")
                    else:
                        self.logger.warning(
                            f"Failed to delete task {task['id']}: {resp.status_code}"
                        )
                except Exception as e:
                    self.logger.warning(f"Failed to delete task {task['id']}: {e}")

            # Add cascade-deleted children to the deleted list
            # (they were automatically deleted by ClickUp when parent tasks were deleted)
            deleted_ids.extend(cascade_deleted_children)

        self.logger.info(
            f"✅ Deleted {len(deleted_ids)} entities (including {len(cascade_deleted_children)} cascade-deleted children)"
        )
        return deleted_ids

    async def cleanup(self):
        """Comprehensive cleanup of ALL test data.

        Cleans up:
        1. Current session entities (tasks, comments, files)
        2. Test list
        3. Test space
        4. Any orphaned test data from failed runs
        """
        self.logger.info("🧹 Starting comprehensive ClickUp cleanup")

        cleanup_stats = {
            "tasks_deleted": 0,
            "subtasks_deleted": 0,
            "comments_deleted": 0,
            "files_deleted": 0,
            "lists_deleted": 0,
            "spaces_deleted": 0,
            "errors": 0,
        }

        try:
            await self._ensure_workspace()

            # 1. Clean up current session entities
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Delete comments
                for comment in self._comments:
                    try:
                        await self._rate_limit()
                        resp = await client.delete(
                            f"{self.API_BASE}/comment/{comment['id']}",
                            headers=self._headers(),
                        )
                        if resp.status_code in (200, 204):
                            cleanup_stats["comments_deleted"] += 1
                    except Exception as e:
                        self.logger.warning(f"Failed to delete comment {comment['id']}: {e}")
                        cleanup_stats["errors"] += 1

                # Delete subtasks
                for subtask in self._subtasks:
                    try:
                        await self._rate_limit()
                        resp = await client.delete(
                            f"{self.API_BASE}/task/{subtask['id']}",
                            headers=self._headers(),
                        )
                        if resp.status_code in (200, 204):
                            cleanup_stats["subtasks_deleted"] += 1
                    except Exception as e:
                        self.logger.warning(f"Failed to delete subtask {subtask['id']}: {e}")
                        cleanup_stats["errors"] += 1

                # Delete tasks
                for task in self._tasks:
                    try:
                        await self._rate_limit()
                        resp = await client.delete(
                            f"{self.API_BASE}/task/{task['id']}",
                            headers=self._headers(),
                        )
                        if resp.status_code in (200, 204):
                            cleanup_stats["tasks_deleted"] += 1
                    except Exception as e:
                        self.logger.warning(f"Failed to delete task {task['id']}: {e}")
                        cleanup_stats["errors"] += 1

                # Delete test list
                if self._list_id:
                    try:
                        await self._rate_limit()
                        resp = await client.delete(
                            f"{self.API_BASE}/list/{self._list_id}",
                            headers=self._headers(),
                        )
                        if resp.status_code in (200, 204):
                            cleanup_stats["lists_deleted"] += 1
                            self.logger.info(f"✅ Deleted test list {self._list_id}")
                    except Exception as e:
                        self.logger.warning(f"Failed to delete list {self._list_id}: {e}")
                        cleanup_stats["errors"] += 1

                # Delete test space
                if self._space_id:
                    try:
                        await self._rate_limit()
                        resp = await client.delete(
                            f"{self.API_BASE}/space/{self._space_id}",
                            headers=self._headers(),
                        )
                        if resp.status_code in (200, 204):
                            cleanup_stats["spaces_deleted"] += 1
                            self.logger.info(f"✅ Deleted test space {self._space_id}")
                    except Exception as e:
                        self.logger.warning(f"Failed to delete space {self._space_id}: {e}")
                        cleanup_stats["errors"] += 1

                # 2. Find and clean up orphaned test spaces
                try:
                    spaces_data = await self._get_with_retry(
                        client, f"{self.API_BASE}/team/{self._workspace_id}/space"
                    )
                    for space in spaces_data.get("spaces", []):
                        if space["name"].startswith("Monke Test Space"):
                            try:
                                await self._rate_limit()
                                resp = await client.delete(
                                    f"{self.API_BASE}/space/{space['id']}",
                                    headers=self._headers(),
                                )
                                if resp.status_code in (200, 204):
                                    cleanup_stats["spaces_deleted"] += 1
                                    self.logger.info(f"✅ Deleted orphaned space {space['id']}")
                            except Exception:
                                cleanup_stats["errors"] += 1
                except Exception as e:
                    self.logger.warning(f"Failed to clean up orphaned spaces: {e}")

            self.logger.info(
                f"🧹 Cleanup completed: {cleanup_stats['tasks_deleted']} tasks, "
                f"{cleanup_stats['subtasks_deleted']} subtasks, "
                f"{cleanup_stats['comments_deleted']} comments, "
                f"{cleanup_stats['lists_deleted']} lists, "
                f"{cleanup_stats['spaces_deleted']} spaces deleted, "
                f"{cleanup_stats['errors']} errors"
            )

        except Exception as e:
            self.logger.error(f"❌ Error during cleanup: {e}")
            # Don't re-raise - cleanup is best-effort

    # Helper methods

    def _headers(self) -> Dict[str, str]:
        """Return auth headers for API requests."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def _rate_limit(self):
        """Simple rate limiting to avoid hitting ClickUp API limits."""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    async def _get_with_retry(self, client: httpx.AsyncClient, url: str, retries: int = 3) -> Dict:
        """Make GET request with retry logic."""
        for attempt in range(retries):
            try:
                await self._rate_limit()
                resp = await client.get(url, headers=self._headers())
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                if attempt == retries - 1:
                    raise
                self.logger.warning(f"Request failed (attempt {attempt + 1}/{retries}): {e}")
                await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff

    async def _ensure_workspace(self):
        """Ensure we have a workspace ID."""
        if self._workspace_id:
            return

        async with httpx.AsyncClient(timeout=30.0) as client:
            teams_data = await self._get_with_retry(client, f"{self.API_BASE}/team")
            teams = teams_data.get("teams", [])

            if not teams:
                raise ValueError("No ClickUp workspaces found")

            # Use the first workspace
            self._workspace_id = teams[0]["id"]
            self.logger.info(f"Using workspace: {teams[0]['name']} ({self._workspace_id})")

    async def _ensure_space(self):
        """Ensure we have a test space."""
        if self._space_id:
            return

        await self._ensure_workspace()

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Create a test space
            space_name = f"Monke Test Space {uuid.uuid4().hex[:8]}"

            await self._rate_limit()
            resp = await client.post(
                f"{self.API_BASE}/team/{self._workspace_id}/space",
                headers=self._headers(),
                json={
                    "name": space_name,
                    "multiple_assignees": True,
                    "features": {
                        "due_dates": {"enabled": True},
                        "time_tracking": {"enabled": True},
                    },
                },
            )
            resp.raise_for_status()
            space = resp.json()

            self._space_id = space["id"]
            self.logger.info(f"Created test space: {space_name} ({self._space_id})")

    async def _ensure_list(self):
        """Ensure we have a test list."""
        if self._list_id:
            return

        await self._ensure_space()

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Create a folderless list directly in the space
            list_name = f"Monke Test List {uuid.uuid4().hex[:8]}"

            await self._rate_limit()
            resp = await client.post(
                f"{self.API_BASE}/space/{self._space_id}/list",
                headers=self._headers(),
                json={
                    "name": list_name,
                },
            )
            resp.raise_for_status()
            list_data = resp.json()

            self._list_id = list_data["id"]
            self.logger.info(f"Created test list: {list_name} ({self._list_id})")
