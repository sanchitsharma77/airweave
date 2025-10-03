"""GitLab-specific bongo implementation.

Creates, updates, and deletes test issues, merge requests, and files via the real GitLab API.
"""

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from monke.bongos.base_bongo import BaseBongo
from monke.utils.logging import get_logger


class GitLabBongo(BaseBongo):
    """Bongo for GitLab that creates projects, issues, and merge requests for end-to-end testing.

    - Uses OAuth access token as a bearer token
    - Embeds a short token in issue/MR descriptions for verification
    - Creates a temporary project to keep test data scoped and easy to clean up
    """

    connector_type = "gitlab"

    API_BASE = "https://gitlab.com/api/v4"

    def __init__(self, credentials: Dict[str, Any], **kwargs):
        """Initialize the GitLab bongo.

        Args:
            credentials: Dict with at least "access_token" (GitLab OAuth token)
            **kwargs: Configuration from config file
        """
        super().__init__(credentials)
        self.access_token: str = credentials["access_token"]
        self.entity_count: int = int(kwargs.get("entity_count", 3))
        self.openai_model: str = kwargs.get("openai_model", "gpt-4.1-mini")
        self.max_concurrency: int = int(kwargs.get("max_concurrency", 3))

        # Runtime state
        self._project_id: Optional[str] = None
        self._project_path: Optional[str] = None
        self._issues: List[Dict[str, Any]] = []
        self._merge_requests: List[Dict[str, Any]] = []
        self._files: List[Dict[str, Any]] = []
        self._branches: List[str] = []

        # Simple rate limiting
        self.last_request_time = 0.0
        self.min_delay = 0.5  # 500ms between requests

        self.logger = get_logger("gitlab_bongo")

    async def create_entities(self) -> List[Dict[str, Any]]:
        """Create test entities (issues, merge requests, files) in a temporary GitLab project.

        Returns a list of created entity descriptors used by the test flow.
        """
        self.logger.info(f"🥁 Creating {self.entity_count} GitLab test entities")
        await self._ensure_project()

        from monke.generation.gitlab import (
            generate_gitlab_file,
            generate_gitlab_issue,
            generate_gitlab_merge_request,
        )

        entities: List[Dict[str, Any]] = []
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async with httpx.AsyncClient() as client:

            async def create_one_issue() -> Optional[Dict[str, Any]]:
                """Create a single issue."""
                async with semaphore:
                    try:
                        await self._rate_limit()
                        token = str(uuid.uuid4())[:8]
                        self.logger.info(f"🔨 Generating issue with token: {token}")
                        title, description, comments = await generate_gitlab_issue(
                            self.openai_model, token
                        )
                        self.logger.info(f"📝 Generated issue: '{title[:50]}...'")

                        # Create issue
                        resp = await client.post(
                            f"{self.API_BASE}/projects/{self._project_id}/issues",
                            headers=self._headers(),
                            json={
                                "title": title,
                                "description": description,
                            },
                        )
                        resp.raise_for_status()
                        issue = resp.json()
                        issue_iid = issue["iid"]

                        # Add comments to the issue
                        for comment_text in comments[:2]:
                            try:
                                await self._rate_limit()
                                note_url = (
                                    f"{self.API_BASE}/projects/{self._project_id}"
                                    f"/issues/{issue_iid}/notes"
                                )
                                await client.post(
                                    note_url,
                                    headers=self._headers(),
                                    json={"body": comment_text},
                                )
                            except Exception as ex:
                                self.logger.warning(
                                    f"Failed to add comment to issue {issue_iid}: {ex}"
                                )

                        # Entity descriptor
                        entity = {
                            "type": "issue",
                            "id": f"{self._project_id}/issues/{issue_iid}",
                            "iid": issue_iid,
                            "name": title,
                            "token": token,
                            "expected_content": token,
                            "path": f"gitlab/issue/{issue_iid}",
                        }
                        self._issues.append(entity)
                        return entity

                    except Exception as e:
                        self.logger.error(
                            f"❌ Error creating issue: {type(e).__name__}: {str(e)}"
                        )
                        raise

            async def create_one_merge_request() -> Optional[Dict[str, Any]]:
                """Create a single merge request."""
                async with semaphore:
                    try:
                        await self._rate_limit()
                        token = str(uuid.uuid4())[:8]

                        # Create a new branch for this MR
                        branch_name = f"test-branch-{token}"
                        self.logger.info(f"🔨 Creating branch {branch_name}")

                        # Create the branch
                        await client.post(
                            f"{self.API_BASE}/projects/{self._project_id}/repository/branches",
                            headers=self._headers(),
                            json={
                                "branch": branch_name,
                                "ref": "main",
                            },
                        )
                        self._branches.append(branch_name)

                        # Create a test file in the branch
                        file_token = str(uuid.uuid4())[:8]
                        file_content, filename = await generate_gitlab_file(
                            self.openai_model, file_token
                        )

                        await self._rate_limit()
                        encoded_filename = quote(filename, safe="")
                        file_url = (
                            f"{self.API_BASE}/projects/{self._project_id}"
                            f"/repository/files/{encoded_filename}"
                        )
                        await client.post(
                            file_url,
                            headers=self._headers(),
                            json={
                                "branch": branch_name,
                                "content": file_content.decode("utf-8"),
                                "commit_message": f"Add test file for {token}",
                            },
                        )

                        # Now generate and create the merge request
                        self.logger.info(f"🔨 Generating MR with token: {token}")
                        (
                            title,
                            description,
                            comments,
                        ) = await generate_gitlab_merge_request(
                            self.openai_model, token, branch_name
                        )
                        self.logger.info(f"📝 Generated MR: '{title[:50]}...'")

                        # Create MR
                        await self._rate_limit()
                        resp = await client.post(
                            f"{self.API_BASE}/projects/{self._project_id}/merge_requests",
                            headers=self._headers(),
                            json={
                                "title": title,
                                "description": description,
                                "source_branch": branch_name,
                                "target_branch": "main",
                            },
                        )
                        resp.raise_for_status()
                        mr = resp.json()
                        mr_iid = mr["iid"]

                        # Add comments to the MR
                        for comment_text in comments[:2]:
                            try:
                                await self._rate_limit()
                                note_url = (
                                    f"{self.API_BASE}/projects/{self._project_id}"
                                    f"/merge_requests/{mr_iid}/notes"
                                )
                                await client.post(
                                    note_url,
                                    headers=self._headers(),
                                    json={"body": comment_text},
                                )
                            except Exception as ex:
                                self.logger.warning(
                                    f"Failed to add comment to MR {mr_iid}: {ex}"
                                )

                        # Entity descriptor
                        entity = {
                            "type": "merge_request",
                            "id": f"{self._project_id}/merge_requests/{mr_iid}",
                            "iid": mr_iid,
                            "name": title,
                            "token": token,
                            "expected_content": token,
                            "path": f"gitlab/merge_request/{mr_iid}",
                            "branch": branch_name,
                        }
                        self._merge_requests.append(entity)
                        return entity

                    except Exception as e:
                        self.logger.error(
                            f"❌ Error creating merge request: {type(e).__name__}: {str(e)}"
                        )
                        raise

            # Create issues and merge requests
            issue_tasks = [create_one_issue() for _ in range(self.entity_count)]
            mr_tasks = [create_one_merge_request() for _ in range(self.entity_count)]

            all_tasks = issue_tasks + mr_tasks
            results = await asyncio.gather(*all_tasks, return_exceptions=True)

            # Process results
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.logger.error(f"Failed to create entity {i + 1}: {result}")
                    raise result
                elif result:
                    entities.append(result)
                    entity_type = result.get("type", "entity")
                    self.logger.info(
                        f"✅ Created {entity_type} {i + 1}: {result['name'][:50]}..."
                    )

        self.created_entities = entities
        return entities

    async def update_entities(self) -> List[Dict[str, Any]]:
        """Update a subset of test entities by regenerating content with same token."""
        self.logger.info("🥁 Updating some GitLab test entities")

        if not self._issues and not self._merge_requests:
            return []

        from monke.generation.gitlab import (
            generate_gitlab_issue,
            generate_gitlab_merge_request,
        )

        updated_entities: List[Dict[str, Any]] = []

        async with httpx.AsyncClient() as client:
            # Update first issue
            if self._issues:
                issue = self._issues[0]
                await self._rate_limit()
                title, description, _ = await generate_gitlab_issue(
                    self.openai_model, issue["token"]
                )

                issue_url = (
                    f"{self.API_BASE}/projects/{self._project_id}/issues/{issue['iid']}"
                )
                resp = await client.put(
                    issue_url,
                    headers=self._headers(),
                    json={"title": title, "description": description},
                )
                resp.raise_for_status()
                updated_entities.append({**issue, "name": title})

            # Update first merge request
            if self._merge_requests:
                mr = self._merge_requests[0]
                await self._rate_limit()
                title, description, _ = await generate_gitlab_merge_request(
                    self.openai_model, mr["token"], mr["branch"]
                )

                mr_url = (
                    f"{self.API_BASE}/projects/{self._project_id}"
                    f"/merge_requests/{mr['iid']}"
                )
                resp = await client.put(
                    mr_url,
                    headers=self._headers(),
                    json={"title": title, "description": description},
                )
                resp.raise_for_status()
                updated_entities.append({**mr, "name": title})

        return updated_entities

    async def delete_entities(self) -> List[str]:
        """Delete all created test entities and the temporary project."""
        self.logger.info("🥁 Deleting all GitLab test entities")
        deleted_ids = await self.delete_specific_entities(self.created_entities)
        await self._delete_project()
        return deleted_ids

    async def delete_specific_entities(
        self, entities: List[Dict[str, Any]]
    ) -> List[str]:
        """Delete provided list of entities by id."""
        self.logger.info(f"🥁 Deleting {len(entities)} GitLab entities")
        deleted: List[str] = []

        async with httpx.AsyncClient() as client:
            for entity in entities:
                try:
                    await self._rate_limit()

                    # Delete based on entity type
                    if entity["type"] == "issue":
                        # GitLab doesn't allow deleting issues via API without admin permissions
                        # We'll close them instead
                        issue_url = (
                            f"{self.API_BASE}/projects/{self._project_id}"
                            f"/issues/{entity['iid']}"
                        )
                        r = await client.put(
                            issue_url,
                            headers=self._headers(),
                            json={"state_event": "close"},
                        )
                        if r.status_code in (200, 204):
                            deleted.append(entity["id"])

                    elif entity["type"] == "merge_request":
                        # Close the merge request
                        mr_url = (
                            f"{self.API_BASE}/projects/{self._project_id}"
                            f"/merge_requests/{entity['iid']}"
                        )
                        r = await client.put(
                            mr_url,
                            headers=self._headers(),
                            json={"state_event": "close"},
                        )
                        if r.status_code in (200, 204):
                            deleted.append(entity["id"])

                except Exception as ex:
                    self.logger.warning(f"Delete error for {entity.get('id')}: {ex}")

        return deleted

    async def cleanup(self):
        """Comprehensive cleanup of all monke test data."""
        self.logger.info("🧹 Starting comprehensive GitLab cleanup")

        cleanup_stats = {"projects_deleted": 0, "entities_closed": 0, "errors": 0}

        try:
            # Clean up current session entities
            if self._issues or self._merge_requests:
                deleted = await self.delete_specific_entities(
                    self._issues + self._merge_requests
                )
                cleanup_stats["entities_closed"] += len(deleted)

            # Delete the test project
            if self._project_id:
                await self._delete_project()
                cleanup_stats["projects_deleted"] += 1

            # Find and clean up orphaned test projects
            orphaned_projects = await self._find_monke_test_projects()
            if orphaned_projects:
                self.logger.info(
                    f"🔍 Found {len(orphaned_projects)} monke test projects to clean up"
                )
                for project in orphaned_projects:
                    try:
                        await self._delete_project_by_id(project["id"])
                        cleanup_stats["projects_deleted"] += 1
                        self.logger.info(
                            f"✅ Deleted project: {project['name']} ({project['id']})"
                        )
                    except Exception as e:
                        cleanup_stats["errors"] += 1
                        self.logger.warning(
                            f"⚠️ Failed to delete project {project['id']}: {e}"
                        )

            self.logger.info(
                f"🧹 Cleanup completed: {cleanup_stats['projects_deleted']} projects, "
                f"{cleanup_stats['entities_closed']} entities closed, {cleanup_stats['errors']} errors"
            )

        except Exception as e:
            self.logger.error(f"❌ Error during cleanup: {e}")

    async def _ensure_project(self):
        """Create a temporary GitLab project for testing."""
        if self._project_id:
            return

        project_name = f"monke-gitlab-test-{str(uuid.uuid4())[:6]}"

        async with httpx.AsyncClient() as client:
            # Create the project
            resp = await client.post(
                f"{self.API_BASE}/projects",
                headers=self._headers(),
                json={
                    "name": project_name,
                    "visibility": "private",
                    "initialize_with_readme": True,
                },
            )
            resp.raise_for_status()
            project = resp.json()

            self._project_id = str(project["id"])
            self._project_path = project["path_with_namespace"]
            self.logger.info(f"Created project {project_name} ({self._project_id})")

    async def _delete_project(self):
        """Delete the temporary project."""
        if not self._project_id:
            return
        await self._delete_project_by_id(self._project_id)
        self._project_id = None

    async def _delete_project_by_id(self, project_id: str):
        """Delete a project by its ID."""
        async with httpx.AsyncClient() as client:
            await self._rate_limit()
            r = await client.delete(
                f"{self.API_BASE}/projects/{project_id}",
                headers=self._headers(),
            )
            if r.status_code in (200, 202, 204):
                self.logger.debug(f"Deleted project {project_id}")
            else:
                self.logger.warning(
                    f"Failed to delete project {project_id}: {r.status_code}"
                )

    async def _find_monke_test_projects(self) -> List[Dict[str, Any]]:
        """Find all monke test projects."""
        monke_projects = []

        async with httpx.AsyncClient() as client:
            await self._rate_limit()
            r = await client.get(
                f"{self.API_BASE}/projects",
                headers=self._headers(),
                params={"owned": True, "simple": True},
            )

            if r.status_code == 200:
                projects = r.json()
                for project in projects:
                    name = project.get("name", "")
                    if name.startswith("monke-gitlab-test-"):
                        monke_projects.append(project)

        return monke_projects

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
