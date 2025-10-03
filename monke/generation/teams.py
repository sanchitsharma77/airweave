"""Microsoft Teams content generation adapter.

Generates realistic message and channel content for testing Teams integration using LLM.
"""

from typing import Dict

from monke.client.llm import LLMClient
from monke.generation.schemas.teams import TeamsChannel, TeamsMessage


async def generate_teams_channel(model: str) -> Dict[str, str]:
    """Generate channel content for Microsoft Teams testing using LLM.

    Args:
        model: The LLM model to use

    Returns:
        Dict with display_name and description
    """
    llm = LLMClient(model_override=model)

    instruction = (
        "Generate a realistic Microsoft Teams channel for a software development team. "
        "The channel should be for a specific topic like a project, feature, or discussion area. "
        "Make it professional and believable."
    )

    channel = await llm.generate_structured(TeamsChannel, instruction)

    return {
        "display_name": channel.spec.display_name,
        "description": channel.spec.description,
    }


async def generate_teams_message(model: str, token: str) -> Dict[str, str]:
    """Generate message content for Microsoft Teams testing using LLM.

    Args:
        model: The LLM model to use
        token: A unique token to embed in the content for verification

    Returns:
        Dict with subject and body content
    """
    llm = LLMClient(model_override=model)

    instruction = (
        "Generate a realistic Microsoft Teams message for a software development team. "
        "The message should be a helpful update, question, or discussion point. "
        f"You MUST include the literal token '{token}' in the message body. "
        "Make it professional and believable, like a real team communication."
    )

    message = await llm.generate_structured(TeamsMessage, instruction)
    message.spec.token = token

    # Ensure token is in the body
    if token not in message.content.body:
        message.content.body += f"\n\n**Verification Token**: {token}"

    return {
        "subject": message.content.subject,
        "body": message.content.body,
    }
