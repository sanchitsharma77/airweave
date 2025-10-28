"""Todoist entity schemas.

Based on the Todoist REST API reference, we define entity schemas for
Todoist objects, Projects, Sections, Tasks, and Comments.
"""

from typing import Any, List, Optional

from airweave.platform.entities._airweave_field import AirweaveField
from airweave.platform.entities._base import BaseEntity


class TodoistProjectEntity(BaseEntity):
    """Schema for Todoist project entities.

    Reference:
        https://developer.todoist.com/rest/v2/#projects
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the project ID)
    # - breadcrumbs (empty - projects are top-level)
    # - name (from project name)
    # - created_at (None - projects don't have creation timestamp)
    # - updated_at (None - projects don't have update timestamp)

    # API fields
    color: Optional[str] = AirweaveField(
        None, description="Color of the project (e.g., 'grey', 'blue')", embeddable=False
    )
    comment_count: int = AirweaveField(
        0, description="Number of comments in the project", embeddable=False
    )
    order: int = AirweaveField(0, description="Project order in the project list", embeddable=False)
    is_shared: bool = AirweaveField(
        False, description="Whether the project is shared with others", embeddable=False
    )
    is_favorite: bool = AirweaveField(
        False, description="Whether the project is marked as a favorite", embeddable=False
    )
    is_inbox_project: bool = AirweaveField(
        False, description="Whether this is the Inbox project", embeddable=False
    )
    is_team_inbox: bool = AirweaveField(
        False, description="Whether this is the team Inbox project", embeddable=False
    )
    view_style: Optional[str] = AirweaveField(
        None, description="Project view style ('list' or 'board')", embeddable=False
    )
    url: Optional[str] = AirweaveField(
        None, description="URL to access the project", embeddable=False
    )
    parent_id: Optional[str] = AirweaveField(
        None, description="ID of the parent project if nested", embeddable=False
    )


class TodoistSectionEntity(BaseEntity):
    """Schema for Todoist section entities.

    Reference:
        https://developer.todoist.com/rest/v2/#sections
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the section ID)
    # - breadcrumbs (project breadcrumb)
    # - name (from section name)
    # - created_at (None - sections don't have creation timestamp)
    # - updated_at (None - sections don't have update timestamp)

    # API fields
    project_id: str = AirweaveField(
        ..., description="ID of the project this section belongs to", embeddable=False
    )
    order: int = AirweaveField(0, description="Section order in the project", embeddable=False)


class TodoistTaskEntity(BaseEntity):
    """Schema for Todoist task entities.

    Reference:
        https://developer.todoist.com/rest/v2/#tasks
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the task ID)
    # - breadcrumbs (project and optionally section breadcrumbs)
    # - name (from task content)
    # - created_at (from created_at timestamp)
    # - updated_at (None - tasks don't have update timestamp)

    # API fields
    content: str = AirweaveField(..., description="The task content/title", embeddable=True)
    description: Optional[str] = AirweaveField(
        None, description="Optional detailed description of the task", embeddable=True
    )
    comment_count: int = AirweaveField(
        0, description="Number of comments on the task", embeddable=False
    )
    is_completed: bool = AirweaveField(
        False, description="Whether the task is completed", embeddable=True
    )
    labels: List[str] = AirweaveField(
        default_factory=list,
        description="List of label names attached to the task",
        embeddable=True,
    )
    order: int = AirweaveField(
        0, description="Task order in the project or section", embeddable=False
    )
    priority: int = AirweaveField(
        1, description="Task priority (1-4, 4 is highest)", ge=1, le=4, embeddable=True
    )
    project_id: Optional[str] = AirweaveField(
        None, description="ID of the project this task belongs to", embeddable=False
    )
    section_id: Optional[str] = AirweaveField(
        None, description="ID of the section this task belongs to", embeddable=False
    )
    parent_id: Optional[str] = AirweaveField(
        None, description="ID of the parent task if subtask", embeddable=False
    )
    creator_id: Optional[str] = AirweaveField(
        None, description="ID of the user who created the task", embeddable=False
    )
    assignee_id: Optional[str] = AirweaveField(
        None, description="ID of the user assigned to the task", embeddable=False
    )
    assigner_id: Optional[str] = AirweaveField(
        None, description="ID of the user who assigned the task", embeddable=False
    )
    due_date: Optional[str] = AirweaveField(
        None, description="Due date in YYYY-MM-DD format", embeddable=True
    )
    due_datetime: Optional[Any] = AirweaveField(
        None, description="Due date and time", embeddable=True
    )
    due_string: Optional[str] = AirweaveField(
        None, description="Original due date string (e.g., 'tomorrow')", embeddable=True
    )
    due_is_recurring: bool = AirweaveField(
        False, description="Whether the task is recurring", embeddable=False
    )
    due_timezone: Optional[str] = AirweaveField(
        None, description="Timezone for the due date", embeddable=False
    )
    deadline_date: Optional[str] = AirweaveField(
        None, description="Deadline date in YYYY-MM-DD format", embeddable=False
    )
    duration_amount: Optional[int] = AirweaveField(
        None, description="Duration amount", embeddable=False
    )
    duration_unit: Optional[str] = AirweaveField(
        None, description="Duration unit ('minute' or 'day')", embeddable=False
    )
    url: Optional[str] = AirweaveField(None, description="URL to access the task", embeddable=False)


class TodoistCommentEntity(BaseEntity):
    """Schema for Todoist comment entities.

    Reference:
        https://developer.todoist.com/rest/v2/#comments
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the comment ID)
    # - breadcrumbs (project, section, and task breadcrumbs)
    # - name (from content preview)
    # - created_at (from posted_at timestamp)
    # - updated_at (None - comments don't have update timestamp)

    # API fields
    task_id: str = AirweaveField(
        ..., description="ID of the task this comment belongs to", embeddable=False
    )
    content: Optional[str] = AirweaveField(None, description="The comment content", embeddable=True)
    posted_at: Any = AirweaveField(..., description="When the comment was posted", embeddable=False)
