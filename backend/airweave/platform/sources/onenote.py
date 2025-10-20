"""Microsoft OneNote source implementation.

Retrieves data from Microsoft OneNote, including:
 - User info (authenticated user)
 - Notebooks the user has access to
 - Section groups within notebooks
 - Sections within notebooks/section groups
 - Pages within sections

Reference:
  https://learn.microsoft.com/en-us/graph/api/resources/onenote
  https://learn.microsoft.com/en-us/graph/api/onenote-list-notebooks
  https://learn.microsoft.com/en-us/graph/api/notebook-list-sections
  https://learn.microsoft.com/en-us/graph/api/section-list-pages
"""

from datetime import datetime
from typing import Any, AsyncGenerator, Dict, Optional
import re

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from airweave.platform.decorators import source
from airweave.platform.entities._base import Breadcrumb, ChunkEntity
from airweave.platform.entities.onenote import (
    OneNoteNotebookEntity,
    OneNotePageEntity,
    OneNoteSectionEntity,
    OneNoteSectionGroupEntity,
    OneNoteUserEntity,
)
from airweave.platform.sources._base import BaseSource
from airweave.schemas.source_connection import AuthenticationMethod, OAuthType


@source(
    name="Microsoft OneNote",
    short_name="onenote",
    auth_methods=[
        AuthenticationMethod.OAUTH_BROWSER,
        AuthenticationMethod.OAUTH_TOKEN,
        AuthenticationMethod.AUTH_PROVIDER,
    ],
    oauth_type=OAuthType.WITH_ROTATING_REFRESH,
    auth_config_class=None,
    config_class="OneNoteConfig",
    labels=["Productivity", "Note Taking", "Collaboration"],
    supports_continuous=False,
)
class OneNoteSource(BaseSource):
    """Microsoft OneNote source connector integrates with the Microsoft Graph API.

    Synchronizes data from Microsoft OneNote including notebooks, sections, section groups,
    and pages.

    It provides comprehensive access to OneNote resources with proper token refresh
    and rate limiting.
    """

    GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

    @classmethod
    async def create(
        cls, access_token: str, config: Optional[Dict[str, Any]] = None
    ) -> "OneNoteSource":
        """Create a new Microsoft OneNote source instance with the provided OAuth access token.

        Args:
            access_token: OAuth access token for Microsoft Graph API
            config: Optional configuration parameters

        Returns:
            Configured OneNoteSource instance
        """
        instance = cls()
        instance.access_token = access_token
        return instance

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True
    )
    async def _get_with_auth(
        self, client: httpx.AsyncClient, url: str, params: Optional[dict] = None
    ) -> dict:
        """Make an authenticated GET request to Microsoft Graph API.

        Args:
            client: HTTP client to use for the request
            url: API endpoint URL
            params: Optional query parameters

        Returns:
            JSON response data
        """
        # Get fresh token (will refresh if needed)
        access_token = await self.get_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        try:
            response = await client.get(url, headers=headers, params=params)

            # Handle 401 errors by refreshing token and retrying
            if response.status_code == 401:
                self.logger.warning(
                    f"Got 401 Unauthorized from Microsoft Graph API at {url}, refreshing token..."
                )
                await self.refresh_on_unauthorized()

                # Get new token and retry
                access_token = await self.get_access_token()
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                }
                response = await client.get(url, headers=headers, params=params)

            # Handle 429 Rate Limit
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "60")
                self.logger.warning(
                    f"Rate limit hit for {url}, waiting {retry_after} seconds before retry"
                )
                import asyncio

                await asyncio.sleep(float(retry_after))
                # Retry after waiting
                response = await client.get(url, headers=headers, params=params)

            response.raise_for_status()
            data = response.json()
            return data
        except Exception as e:
            self.logger.error(f"Error in API request to {url}: {str(e)}")
            raise

    def _parse_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        """Parse datetime string from Microsoft Graph API format.

        Args:
            dt_str: DateTime string from API

        Returns:
            Parsed datetime object or None
        """
        if not dt_str:
            return None
        try:
            if dt_str.endswith("Z"):
                dt_str = dt_str.replace("Z", "+00:00")
            return datetime.fromisoformat(dt_str)
        except (ValueError, TypeError) as e:
            self.logger.warning(f"Error parsing datetime {dt_str}: {str(e)}")
            return None

    def _strip_html_tags(self, html_content: Optional[str]) -> Optional[str]:
        """Strip HTML tags from content for better text search.

        Args:
            html_content: HTML content string

        Returns:
            Plain text content or None
        """
        if not html_content:
            return None
        try:
            # Remove HTML tags
            text = re.sub(r"<[^>]+>", " ", html_content)
            # Remove extra whitespace
            text = re.sub(r"\s+", " ", text).strip()
            return text if text else None
        except Exception as e:
            self.logger.warning(f"Error stripping HTML tags: {str(e)}")
            return html_content

    async def _generate_user_entity(
        self, client: httpx.AsyncClient
    ) -> AsyncGenerator[OneNoteUserEntity, None]:
        """Generate OneNoteUserEntity for the authenticated user.

        Args:
            client: HTTP client for API requests

        Yields:
            OneNoteUserEntity object
        """
        self.logger.info("Fetching authenticated user information")
        url = f"{self.GRAPH_BASE_URL}/me"
        params = {
            "$select": "id,displayName,userPrincipalName,mail,jobTitle,department,officeLocation"
        }

        try:
            user_data = await self._get_with_auth(client, url, params=params)
            user_id = user_data.get("id")
            display_name = user_data.get("displayName", "Unknown User")

            self.logger.debug(f"Processing user: {display_name}")

            yield OneNoteUserEntity(
                entity_id=user_id,
                breadcrumbs=[],
                display_name=display_name,
                user_principal_name=user_data.get("userPrincipalName"),
                mail=user_data.get("mail"),
                job_title=user_data.get("jobTitle"),
                department=user_data.get("department"),
                office_location=user_data.get("officeLocation"),
            )

            self.logger.info("Completed user entity generation")

        except Exception as e:
            self.logger.error(f"Error generating user entity: {str(e)}")
            # Don't raise - continue with other entities

    async def _generate_notebook_entities(
        self, client: httpx.AsyncClient
    ) -> AsyncGenerator[OneNoteNotebookEntity, None]:
        """Generate OneNoteNotebookEntity objects for user's notebooks.

        Args:
            client: HTTP client for API requests

        Yields:
            OneNoteNotebookEntity objects
        """
        self.logger.info("Starting notebook entity generation")
        url = f"{self.GRAPH_BASE_URL}/me/onenote/notebooks"
        params = {"$top": 100}

        try:
            notebook_count = 0
            while url:
                self.logger.debug(f"Fetching notebooks from: {url}")
                data = await self._get_with_auth(client, url, params=params)
                notebooks = data.get("value", [])
                self.logger.info(f"Retrieved {len(notebooks)} notebooks")

                for notebook_data in notebooks:
                    notebook_count += 1
                    notebook_id = notebook_data.get("id")
                    display_name = notebook_data.get("displayName", "Unknown Notebook")

                    self.logger.debug(f"Processing notebook #{notebook_count}: {display_name}")

                    yield OneNoteNotebookEntity(
                        entity_id=notebook_id,
                        breadcrumbs=[],
                        display_name=display_name,
                        is_default=notebook_data.get("isDefault"),
                        is_shared=notebook_data.get("isShared"),
                        user_role=notebook_data.get("userRole"),
                        created_datetime=self._parse_datetime(notebook_data.get("createdDateTime")),
                        last_modified_datetime=self._parse_datetime(
                            notebook_data.get("lastModifiedDateTime")
                        ),
                        created_by=notebook_data.get("createdBy"),
                        last_modified_by=notebook_data.get("lastModifiedBy"),
                        links=notebook_data.get("links"),
                        self_url=notebook_data.get("self"),
                    )

                # Handle pagination
                url = data.get("@odata.nextLink")
                if url:
                    self.logger.debug("Following pagination to next page")
                    params = None  # params are included in the nextLink

            self.logger.info(f"Completed notebook generation. Total notebooks: {notebook_count}")

        except Exception as e:
            self.logger.error(f"Error generating notebook entities: {str(e)}")
            raise

    async def _generate_section_group_entities(
        self, client: httpx.AsyncClient, notebook_id: str, notebook_name: str
    ) -> AsyncGenerator[OneNoteSectionGroupEntity, None]:
        """Generate OneNoteSectionGroupEntity objects for section groups in a notebook.

        Args:
            client: HTTP client for API requests
            notebook_id: ID of the notebook
            notebook_name: Name of the notebook

        Yields:
            OneNoteSectionGroupEntity objects
        """
        self.logger.info(f"Starting section group entity generation for notebook: {notebook_name}")
        url = f"{self.GRAPH_BASE_URL}/me/onenote/notebooks/{notebook_id}/sectionGroups"
        params = {"$top": 100}

        try:
            section_group_count = 0
            while url:
                self.logger.debug(f"Fetching section groups from: {url}")
                data = await self._get_with_auth(client, url, params=params)
                section_groups = data.get("value", [])
                self.logger.info(
                    f"Retrieved {len(section_groups)} section groups for notebook {notebook_name}"
                )

                for sg_data in section_groups:
                    section_group_count += 1
                    sg_id = sg_data.get("id")
                    display_name = sg_data.get("displayName", "Unknown Section Group")

                    self.logger.debug(f"Processing section group #{section_group_count}: {display_name}")

                    yield OneNoteSectionGroupEntity(
                        entity_id=sg_id,
                        breadcrumbs=[
                            Breadcrumb(entity_id=notebook_id, name=notebook_name[:50], type="notebook")
                        ],
                        notebook_id=notebook_id,
                        parent_section_group_id=sg_data.get("parentSectionGroupId"),
                        display_name=display_name,
                        created_datetime=self._parse_datetime(sg_data.get("createdDateTime")),
                        last_modified_datetime=self._parse_datetime(
                            sg_data.get("lastModifiedDateTime")
                        ),
                        created_by=sg_data.get("createdBy"),
                        last_modified_by=sg_data.get("lastModifiedBy"),
                        sections_url=sg_data.get("sectionsUrl"),
                        section_groups_url=sg_data.get("sectionGroupsUrl"),
                    )

                # Handle pagination
                url = data.get("@odata.nextLink")
                if url:
                    self.logger.debug("Following pagination to next page")
                    params = None

            self.logger.info(
                f"Completed section group generation for notebook {notebook_name}. "
                f"Total section groups: {section_group_count}"
            )

        except Exception as e:
            self.logger.error(
                f"Error generating section group entities for notebook {notebook_name}: {str(e)}"
            )
            # Don't raise - continue with other notebooks

    async def _generate_section_entities(
        self,
        client: httpx.AsyncClient,
        notebook_id: str,
        notebook_name: str,
        notebook_breadcrumb: Breadcrumb,
    ) -> AsyncGenerator[OneNoteSectionEntity, None]:
        """Generate OneNoteSectionEntity objects for sections in a notebook.

        Args:
            client: HTTP client for API requests
            notebook_id: ID of the notebook
            notebook_name: Name of the notebook
            notebook_breadcrumb: Breadcrumb for the notebook

        Yields:
            OneNoteSectionEntity objects
        """
        self.logger.info(f"Starting section entity generation for notebook: {notebook_name}")
        url = f"{self.GRAPH_BASE_URL}/me/onenote/notebooks/{notebook_id}/sections"
        params = {"$top": 100}

        try:
            section_count = 0
            while url:
                self.logger.debug(f"Fetching sections from: {url}")
                data = await self._get_with_auth(client, url, params=params)
                sections = data.get("value", [])
                self.logger.info(f"Retrieved {len(sections)} sections for notebook {notebook_name}")

                for section_data in sections:
                    section_count += 1
                    section_id = section_data.get("id")
                    display_name = section_data.get("displayName", "Unknown Section")

                    self.logger.debug(f"Processing section #{section_count}: {display_name}")

                    yield OneNoteSectionEntity(
                        entity_id=section_id,
                        breadcrumbs=[notebook_breadcrumb],
                        notebook_id=notebook_id,
                        parent_section_group_id=section_data.get("parentSectionGroupId"),
                        display_name=display_name,
                        is_default=section_data.get("isDefault"),
                        created_datetime=self._parse_datetime(section_data.get("createdDateTime")),
                        last_modified_datetime=self._parse_datetime(
                            section_data.get("lastModifiedDateTime")
                        ),
                        created_by=section_data.get("createdBy"),
                        last_modified_by=section_data.get("lastModifiedBy"),
                        pages_url=section_data.get("pagesUrl"),
                    )

                # Handle pagination
                url = data.get("@odata.nextLink")
                if url:
                    self.logger.debug("Following pagination to next page")
                    params = None

            self.logger.info(
                f"Completed section generation for notebook {notebook_name}. "
                f"Total sections: {section_count}"
            )

        except Exception as e:
            self.logger.error(
                f"Error generating section entities for notebook {notebook_name}: {str(e)}"
            )
            # Don't raise - continue with other notebooks

    async def _generate_page_entities(
        self,
        client: httpx.AsyncClient,
        section_id: str,
        section_name: str,
        notebook_id: str,
        section_breadcrumbs: list[Breadcrumb],
    ) -> AsyncGenerator[OneNotePageEntity, None]:
        """Generate OneNotePageEntity objects for pages in a section.

        Args:
            client: HTTP client for API requests
            section_id: ID of the section
            section_name: Name of the section
            notebook_id: ID of the notebook
            section_breadcrumbs: Breadcrumbs for the section

        Yields:
            OneNotePageEntity objects
        """
        self.logger.info(f"Starting page generation for section: {section_name}")
        url = f"{self.GRAPH_BASE_URL}/me/onenote/sections/{section_id}/pages"
        params = {"$top": 50}

        try:
            page_count = 0
            while url:
                self.logger.debug(f"Fetching pages from: {url}")
                data = await self._get_with_auth(client, url, params=params)
                pages = data.get("value", [])
                self.logger.info(f"Retrieved {len(pages)} pages for section {section_name}")

                for page_data in pages:
                    page_count += 1
                    page_id = page_data.get("id")
                    title = page_data.get("title", "Untitled Page")

                    self.logger.debug(f"Processing page #{page_count}: {title}")

                    # Fetch page content if contentUrl is available
                    content = None
                    content_url = page_data.get("contentUrl")
                    if content_url:
                        try:
                            # Get the HTML content of the page
                            content_response = await self._get_with_auth(client, content_url)
                            # content_response is already parsed as dict/str depending on response
                            if isinstance(content_response, str):
                                content = self._strip_html_tags(content_response)
                            elif isinstance(content_response, bytes):
                                content = self._strip_html_tags(content_response.decode("utf-8"))
                        except Exception as e:
                            self.logger.warning(
                                f"Failed to fetch content for page {title}: {str(e)}"
                            )

                    yield OneNotePageEntity(
                        entity_id=page_id,
                        breadcrumbs=section_breadcrumbs,
                        notebook_id=notebook_id,
                        section_id=section_id,
                        title=title,
                        content=content,
                        content_url=content_url,
                        level=page_data.get("level"),
                        order=page_data.get("order"),
                        created_datetime=self._parse_datetime(page_data.get("createdDateTime")),
                        last_modified_datetime=self._parse_datetime(
                            page_data.get("lastModifiedDateTime")
                        ),
                        created_by=page_data.get("createdBy"),
                        last_modified_by=page_data.get("lastModifiedBy"),
                        links=page_data.get("links"),
                        user_tags=page_data.get("userTags", []),
                    )

                # Handle pagination
                url = data.get("@odata.nextLink")
                if url:
                    self.logger.debug("Following pagination to next page")
                    params = None

            self.logger.info(
                f"Completed page generation for section {section_name}. Total pages: {page_count}"
            )

        except Exception as e:
            self.logger.error(f"Error generating pages for section {section_name}: {str(e)}")
            # Don't raise - continue with other sections

    async def generate_entities(self) -> AsyncGenerator[ChunkEntity, None]:
        """Generate all Microsoft OneNote entities.

        Yields entities in the following order:
          - OneNoteUserEntity for the authenticated user
          - OneNoteNotebookEntity for user's notebooks
          - OneNoteSectionGroupEntity for section groups in each notebook
          - OneNoteSectionEntity for sections in each notebook
          - OneNotePageEntity for pages in each section
        """
        self.logger.info("===== STARTING MICROSOFT ONENOTE ENTITY GENERATION =====")
        entity_count = 0

        try:
            async with self.http_client() as client:
                self.logger.info("HTTP client created, starting entity generation")

                # 1) Generate user entity
                self.logger.info("Generating user entity...")
                async for user_entity in self._generate_user_entity(client):
                    entity_count += 1
                    self.logger.debug(
                        f"Yielding entity #{entity_count}: User - {user_entity.display_name}"
                    )
                    yield user_entity

                # 2) Generate notebook entities
                self.logger.info("Generating notebook entities...")
                async for notebook_entity in self._generate_notebook_entities(client):
                    entity_count += 1
                    self.logger.info(
                        f"Yielding entity #{entity_count}: Notebook - {notebook_entity.display_name}"
                    )
                    yield notebook_entity

                    # Create notebook breadcrumb
                    notebook_id = notebook_entity.entity_id
                    notebook_name = notebook_entity.display_name
                    notebook_breadcrumb = Breadcrumb(
                        entity_id=notebook_id, name=notebook_name[:50], type="notebook"
                    )

                    # 3) Generate section groups for this notebook
                    async for section_group_entity in self._generate_section_group_entities(
                        client, notebook_id, notebook_name
                    ):
                        entity_count += 1
                        self.logger.info(
                            f"Yielding entity #{entity_count}: SectionGroup - {section_group_entity.display_name}"
                        )
                        yield section_group_entity

                    # 4) Generate sections for this notebook
                    async for section_entity in self._generate_section_entities(
                        client, notebook_id, notebook_name, notebook_breadcrumb
                    ):
                        entity_count += 1
                        section_display = section_entity.display_name
                        self.logger.info(
                            f"Yielding entity #{entity_count}: Section - {section_display}"
                        )
                        yield section_entity

                        # Create section breadcrumb
                        section_id = section_entity.entity_id
                        section_name = section_entity.display_name
                        section_breadcrumb = Breadcrumb(
                            entity_id=section_id, name=section_name[:50], type="section"
                        )
                        section_breadcrumbs = [notebook_breadcrumb, section_breadcrumb]

                        # 5) Generate pages for this section
                        async for page_entity in self._generate_page_entities(
                            client, section_id, section_name, notebook_id, section_breadcrumbs
                        ):
                            entity_count += 1
                            self.logger.debug(
                                f"Yielding entity #{entity_count}: Page - {page_entity.title}"
                            )
                            yield page_entity

        except Exception as e:
            self.logger.error(f"Error in entity generation: {str(e)}", exc_info=True)
            raise
        finally:
            self.logger.info(
                f"===== MICROSOFT ONENOTE ENTITY GENERATION COMPLETE: {entity_count} entities ====="
            )

    async def validate(self) -> bool:
        """Verify Microsoft OneNote OAuth2 token by pinging the notebooks endpoint.

        Returns:
            True if token is valid, False otherwise
        """
        return await self._validate_oauth2(
            ping_url=f"{self.GRAPH_BASE_URL}/me/onenote/notebooks?$top=1",
            headers={"Accept": "application/json"},
            timeout=10.0,
        )

