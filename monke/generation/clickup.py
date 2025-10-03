"""ClickUp content generation adapter.

Generates realistic task, subtask, comment, and file content for testing ClickUp integration using LLM.
"""

from typing import Tuple

from monke.generation.schemas.clickup import (
    ClickUpTask,
    ClickUpSubtask,
    ClickUpCommentContent,
    ClickUpFileContent,
)
from monke.client.llm import LLMClient


def render_task_description(task: ClickUpTask) -> str:
    """Render the task content as markdown description for ClickUp."""
    content = task.content
    spec = task.spec

    # Build the description in markdown format
    parts = [
        f"## Task Description\n\n{content.description}",
        f"\n**Verification Token**: {spec.token}",
        "\n### Objectives:",
    ]

    # Add objectives as bullet points
    for obj in content.objectives:
        parts.append(f"- {obj}")

    parts.extend(
        [
            f"\n### Technical Details\n\n{content.technical_details}",
            "\n### Acceptance Criteria:",
        ]
    )

    # Add acceptance criteria as checklist
    for criteria in content.acceptance_criteria:
        parts.append(f"- [ ] {criteria}")

    # Add priority and tags
    parts.extend(
        [
            f"\n### Priority: {spec.priority.title()}",
            f"### Tags: {', '.join(spec.tags) if spec.tags else 'None'}",
        ]
    )

    return "\n".join(parts)


def render_subtask_description(subtask: ClickUpSubtask) -> str:
    """Render the subtask content as markdown description for ClickUp."""
    content = subtask.content
    spec = subtask.spec

    parts = [
        f"{content.description}",
        f"\n**Verification Token**: {spec.token}",
    ]

    if content.notes:
        parts.append("\n### Notes:")
        for note in content.notes:
            parts.append(f"- {note}")

    return "\n".join(parts)


async def generate_clickup_task(model: str, token: str) -> Tuple[str, str]:
    """Generate task content for ClickUp testing using LLM.

    Args:
        model: The LLM model to use
        token: A unique token to embed in the content for verification

    Returns:
        Tuple of (task_name, description)
    """
    llm = LLMClient(model_override=model)

    instruction = (
        "Generate a realistic ClickUp task for a software development project. "
        "The task should be technical but believable, like something from a real sprint. "
        f"You MUST include the literal token '{token}' at the beginning of the task name. "
        "Create meaningful objectives, technical details, and acceptance criteria. "
        "The task should feel like it's part of an ongoing project."
    )

    # Generate structured task data
    task = await llm.generate_structured(ClickUpTask, instruction)

    # Ensure token is in the task
    task.spec.token = token

    # Ensure the token appears in the description
    if token not in task.content.description:
        task.content.description += f"\n\n**Debug Token**: {token}"

    # Render the description
    description = render_task_description(task)

    return task.spec.name, description


async def generate_clickup_subtask(
    model: str, token: str, parent_task_name: str
) -> Tuple[str, str]:
    """Generate subtask content for ClickUp testing using LLM.

    Args:
        model: The LLM model to use
        token: A unique token to embed in the content for verification
        parent_task_name: Name of the parent task for context

    Returns:
        Tuple of (subtask_name, description)
    """
    llm = LLMClient(model_override=model)

    instruction = (
        f"Generate a realistic ClickUp subtask for the parent task: '{parent_task_name}'. "
        "The subtask should be a specific, actionable breakdown of work. "
        f"You MUST include the literal token '{token}' at the beginning of the subtask name. "
        "Keep it focused and technical."
    )

    # Generate structured subtask data
    subtask = await llm.generate_structured(ClickUpSubtask, instruction)

    # Ensure token is in the subtask
    subtask.spec.token = token

    # Ensure the token appears in the description
    if token not in subtask.content.description:
        subtask.content.description += f"\n\n**Token**: {token}"

    # Render the description
    description = render_subtask_description(subtask)

    return subtask.spec.name, description


async def generate_clickup_comment(model: str, token: str) -> str:
    """Generate comment content for ClickUp testing using LLM.

    Args:
        model: The LLM model to use
        token: A unique token to embed in the content for verification

    Returns:
        Comment text
    """
    llm = LLMClient(model_override=model)

    instruction = (
        "Generate a realistic ClickUp comment on a task. "
        "It should be helpful, professional, and relevant to software development. "
        f"You MUST include the literal token '{token}' at the beginning of the comment. "
        "It could be a status update, question, or suggestion."
    )

    # Generate structured comment data
    comment = await llm.generate_structured(ClickUpCommentContent, instruction)

    # Ensure token is in the comment
    if token not in comment.text:
        comment.text = f"{token} - {comment.text}"

    return comment.text


async def generate_clickup_file(model: str, token: str) -> Tuple[str, str]:
    """Generate file content for ClickUp testing using LLM.

    Args:
        model: The LLM model to use
        token: A unique token to embed in the content for verification

    Returns:
        Tuple of (filename, file_content)
    """
    llm = LLMClient(model_override=model)

    instruction = (
        "Generate a realistic file attachment for a ClickUp task. "
        "It should be a technical document like a spec, API doc, or requirements file. "
        f"You MUST include the literal token '{token}' at the beginning of the file content. "
        "Make it look like a real project document in markdown format."
    )

    # Generate structured file data
    file_data = await llm.generate_structured(ClickUpFileContent, instruction)

    # Ensure token is in the content
    if token not in file_data.content:
        file_data.content = f"**Verification Token**: {token}\n\n{file_data.content}"

    return file_data.filename, file_data.content
