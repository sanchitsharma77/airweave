"""GitLab content generation adapter.

Generates realistic issue, merge request, and file content for testing GitLab integration using LLM.
"""

from typing import List, Tuple

from monke.generation.schemas.gitlab import (
    GitLabIssue,
    GitLabMergeRequest,
    GitLabFileContent,
)
from monke.client.llm import LLMClient


async def generate_gitlab_issue(model: str, token: str) -> Tuple[str, str, List[str]]:
    """Generate issue content for GitLab testing using LLM.

    Args:
        model: The LLM model to use
        token: A unique token to embed in the content for verification

    Returns:
        Tuple of (title, description, comments)
    """
    llm = LLMClient(model_override=model)

    instruction = (
        "Generate a realistic GitLab issue for a software development project. "
        "The issue should be technical but believable, like something from a real sprint. "
        f"You MUST include the literal token '{token}' in the issue description and in the title. "
        "Create meaningful acceptance criteria. "
        "The issue should feel like it's part of an ongoing project. "
        "Generate 2-3 helpful comments that a developer or project manager might add."
    )

    # Generate structured issue data
    issue = await llm.generate_structured(GitLabIssue, instruction)

    # Ensure token is in the issue
    issue.spec.token = token

    # Ensure the token appears in the title
    if token not in issue.spec.title:
        issue.spec.title = f"{issue.spec.title} [{token}]"

    # Also ensure the token appears in the description if it's not already there
    if token not in issue.content.description:
        issue.content.description += f"\n\n**Verification Token**: {token}"

    # Build the description
    description_parts = [
        issue.content.description,
        "\n### Acceptance Criteria:",
    ]
    for criteria in issue.content.acceptance_criteria:
        description_parts.append(f"- [ ] {criteria}")

    description = "\n".join(description_parts)

    # Return title, description, and comments
    return issue.spec.title, description, issue.content.comments


async def generate_gitlab_merge_request(
    model: str, token: str, source_branch: str
) -> Tuple[str, str, List[str]]:
    """Generate merge request content for GitLab testing using LLM.

    Args:
        model: The LLM model to use
        token: A unique token to embed in the content for verification
        source_branch: Source branch name

    Returns:
        Tuple of (title, description, comments)
    """
    llm = LLMClient(model_override=model)

    instruction = (
        "Generate a realistic GitLab merge request for a software development project. "
        f"You MUST include the literal token '{token}' in the merge request description and title. "
        "The merge request should describe meaningful code changes. "
        "Generate 2-3 comments that reviewers might add."
    )

    # Generate structured MR data
    mr = await llm.generate_structured(GitLabMergeRequest, instruction)

    # Ensure token and branch are set
    mr.spec.token = token
    mr.spec.source_branch = source_branch

    # Ensure the token appears in the title
    if token not in mr.spec.title:
        mr.spec.title = f"{mr.spec.title} [{token}]"

    # Ensure token appears in description
    if token not in mr.content.description:
        mr.content.description += f"\n\n**Verification Token**: {token}"

    # Build the description
    description_parts = [
        mr.content.description,
        "\n### Changes:",
    ]
    for change in mr.content.changes:
        description_parts.append(f"- {change}")

    description = "\n".join(description_parts)

    # Return title, description, and comments
    return mr.spec.title, description, mr.content.comments


async def generate_gitlab_file(model: str, token: str) -> Tuple[bytes, str]:
    """Generate file content for GitLab testing using LLM.

    Args:
        model: The LLM model to use
        token: A unique token to embed in the content for verification

    Returns:
        Tuple of (file_bytes, filename)
    """
    llm = LLMClient(model_override=model)

    instruction = (
        f"Generate content for a Python code file or technical document. "
        f"You MUST include the literal token '{token}' as a comment or in the content. "
        f"Make it look like real code or documentation."
    )

    file_data = await llm.generate_structured(GitLabFileContent, instruction)

    # Ensure token is present
    if token not in file_data.content:
        file_data.content = f"# Verification Token: {token}\n\n" + file_data.content

    # Convert to bytes
    content_bytes = file_data.content.encode("utf-8")

    return content_bytes, file_data.filename
