"""Box content generation adapter.

Generates realistic test content using LLM.
"""

from typing import Tuple

from monke.client.llm import LLMClient
from monke.generation.schemas.box import BoxComment, BoxFile, BoxFolder


async def generate_folder(model: str, token: str) -> dict:
    """Generate folder content with embedded verification token.

    Args:
        model: LLM model to use
        token: Unique token to embed in content

    Returns:
        Dict with folder name and description
    """
    llm = LLMClient(model_override=model)

    instruction = (
        f"Generate a realistic folder for a business/project organization system. "
        f"You MUST include the literal token '{token}' in the description. "
        f"The folder should be business-related and believable."
    )

    folder = await llm.generate_structured(BoxFolder, instruction)
    folder.spec.token = token

    # Ensure token appears in description
    if token not in folder.content.description:
        folder.content.description += f"\n\nVerification Token: {token}"

    return {
        "name": folder.spec.name,
        "description": folder.content.description,
        "purpose": folder.content.purpose,
    }


async def generate_file(model: str, token: str) -> Tuple[bytes, str, str]:
    """Generate file content with embedded verification token.

    Args:
        model: LLM model to use
        token: Unique token to embed in content

    Returns:
        Tuple of (file_bytes, filename, description)
    """
    llm = LLMClient(model_override=model)

    instruction = (
        f"Generate content for a business document or report as plain text. "
        f"You MUST include the literal token '{token}' in the content. "
        f"Make it look like a real business document. "
        f"The filename should end with .txt extension."
    )

    file_data = await llm.generate_structured(BoxFile, instruction)
    file_data.spec.token = token

    # Ensure token is present
    if token not in file_data.content.content:
        file_data.content.content += f"\n\nVerification Token: {token}"

    # Ensure filename has .txt extension
    filename = file_data.content.filename
    if not filename.endswith(".txt"):
        # Remove any existing extension and add .txt
        base_name = filename.rsplit(".", 1)[0] if "." in filename else filename
        filename = f"{base_name}.txt"

    # Convert to bytes
    content_bytes = file_data.content.content.encode("utf-8")

    return content_bytes, filename, file_data.content.description


async def generate_comment(model: str, token: str) -> dict:
    """Generate comment content with embedded verification token.

    Args:
        model: LLM model to use
        token: Unique token to embed in content

    Returns:
        Dict with comment message
    """
    llm = LLMClient(model_override=model)

    instruction = (
        f"Generate a helpful comment on a business document or file. "
        f"You MUST include the literal token '{token}' in the comment text. "
        f"The comment should add value, like feedback, a question, or an update."
    )

    comment = await llm.generate_structured(BoxComment, instruction)
    comment.spec.token = token

    # Ensure token is present
    if token not in comment.content.message:
        comment.content.message += f"\n\nToken: {token}"

    return {"message": comment.content.message}
