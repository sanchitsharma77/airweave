"""SharePoint content generation adapter.

Generates realistic document content for testing SharePoint integration using LLM.
"""

from typing import Tuple

from monke.generation.schemas.sharepoint import SharePointFile, SharePointFolderSpec
from monke.client.llm import LLMClient


def render_document_content(file_data: SharePointFile) -> str:
    """Render the document content as formatted text."""
    content = file_data.content
    spec = file_data.spec

    # Build the document
    parts = [
        f"# {content.title}",
        f"\n**Verification Token**: {spec.token}",
        f"\n## Summary\n\n{content.summary}" if content.summary else "",
        f"\n## Main Content\n\n{content.content}",
    ]

    # Add sections if present
    if content.sections:
        parts.append("\n## Additional Sections\n")
        for i, section in enumerate(content.sections, 1):
            parts.append(f"\n### Section {i}\n\n{section}")

    # Ensure token appears in content
    full_content = "\n".join(parts)
    if spec.token not in full_content:
        full_content += f"\n\n---\n\n**Debug Token**: {spec.token}"

    return full_content


async def generate_sharepoint_file(model: str, token: str) -> Tuple[str, str, str]:
    """Generate file content for SharePoint testing using LLM.

    Args:
        model: The LLM model to use
        token: A unique token to embed in the content for verification

    Returns:
        Tuple of (filename, content, mime_type)
    """
    llm = LLMClient(model_override=model)

    instruction = (
        "Generate a realistic document for a business or technical project. "
        "The document should look professional and contain meaningful content. "
        f"You MUST include the literal token '{token}' in the content. "
        "Create a proper title, summary, and detailed content. "
        "The document should feel like something you'd find in a company SharePoint site. "
        "Examples: project plans, meeting notes, technical specifications, policy documents. "
        "IMPORTANT: The filename MUST end with .txt or .md extension ONLY (not .docx). "
        "Generate plain text or markdown content."
    )

    # Generate structured file data
    file_data = await llm.generate_structured(SharePointFile, instruction)

    # Ensure token is set
    file_data.spec.token = token

    # Make filename unique by including the token
    # This prevents files from overwriting each other when uploaded to SharePoint
    base_name = file_data.spec.filename
    if "." in base_name:
        name_part, ext = base_name.rsplit(".", 1)
        unique_filename = f"{name_part}_{token}.{ext}"
    else:
        unique_filename = f"{base_name}_{token}.txt"

    # Ensure token appears in content
    if token not in file_data.content.content:
        file_data.content.content += f"\n\n**Verification Token**: {token}"

    # Render the content
    rendered_content = render_document_content(file_data)

    # Return unique filename, content, and mime type
    return unique_filename, rendered_content, file_data.spec.file_type


async def generate_folder_name(model: str) -> Tuple[str, str]:
    """Generate a folder name and description for SharePoint.

    Args:
        model: The LLM model to use

    Returns:
        Tuple of (folder_name, description)
    """
    llm = LLMClient(model_override=model)

    instruction = (
        "Generate a realistic folder name for organizing documents in a company SharePoint site. "
        "The folder should have a professional name that would fit in a business context. "
        "Examples: 'Q4 Planning', 'Engineering Docs', 'Marketing Materials', 'Project Phoenix'."
    )

    folder_spec = await llm.generate_structured(SharePointFolderSpec, instruction)

    return folder_spec.name, folder_spec.description


async def generate_sharepoint_list(model: str, token: str) -> Tuple[str, str]:
    """Generate list metadata for SharePoint testing using LLM.

    Args:
        model: The LLM model to use
        token: A unique token to embed in the description

    Returns:
        Tuple of (display_name, description)
    """
    from monke.generation.schemas.sharepoint import SharePointListSpec

    llm = LLMClient(model_override=model)

    instruction = (
        "Generate a realistic SharePoint list for tracking business data. "
        "The list should have a professional name that fits in a business context. "
        f"You MUST include the literal token '{token}' in the description. "
        "Examples: 'Project Tracker', 'Issue Log', 'Team Tasks', 'Inventory Management'."
    )

    list_spec = await llm.generate_structured(SharePointListSpec, instruction)
    list_spec.token = token

    # Ensure token in description
    if token not in list_spec.description:
        list_spec.description += f" (Token: {token})"

    return list_spec.display_name, list_spec.description


async def generate_list_item(model: str, token: str) -> dict:
    """Generate list item content for SharePoint testing using LLM.

    Args:
        model: The LLM model to use
        token: A unique token to embed in the content

    Returns:
        Dict with Title and other fields
    """
    from monke.generation.schemas.sharepoint import SharePointListItemContent

    llm = LLMClient(model_override=model)

    instruction = (
        "Generate realistic content for a SharePoint list item (like a task or project entry). "
        f"You MUST include the literal token '{token}' in the title field. "
        "Create meaningful title and description that would fit in a business list."
    )

    item_content = await llm.generate_structured(SharePointListItemContent, instruction)

    # Ensure token in title
    if token not in item_content.title:
        item_content.title += f" [{token}]"

    return {
        "Title": item_content.title,
        "Description": item_content.description,
        **item_content.additional_fields,
    }


async def generate_page_content(model: str, token: str) -> Tuple[str, str, str]:
    """Generate page content for SharePoint testing using LLM.

    Args:
        model: The LLM model to use
        token: A unique token to embed in the content

    Returns:
        Tuple of (title, content, description)
    """
    from monke.generation.schemas.sharepoint import SharePointPageContent

    llm = LLMClient(model_override=model)

    instruction = (
        "Generate realistic content for a SharePoint site page (like a news article or wiki page). "
        f"You MUST include the literal token '{token}' in the content. "
        "Create a professional page with title, description, and rich content. "
        "Examples: company news, team updates, documentation pages."
    )

    page_content = await llm.generate_structured(SharePointPageContent, instruction)

    # Ensure token in content
    if token not in page_content.content:
        page_content.content += f"\n\n**Verification Token**: {token}"

    return page_content.title, page_content.content, page_content.description
