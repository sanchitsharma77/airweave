"""Trello content generation adapter.

Generates realistic test content for Trello cards and checklists using LLM.
"""

from typing import Any, Dict, List, Tuple

from monke.client.llm import LLMClient
from monke.generation.schemas.trello import TrelloCard, TrelloChecklistContent


async def generate_trello_card(model: str, token: str) -> Tuple[str, str, List[str]]:
    """Generate card content for Trello testing using LLM.

    Args:
        model: The LLM model to use
        token: A unique token to embed in the content for verification

    Returns:
        Tuple of (title, description, labels)
    """
    llm = LLMClient(model_override=model)

    instruction = (
        f"Generate a realistic Trello card for a software development project. "
        f"The card should be technical but believable, like something from a real sprint board. "
        f"You MUST include the literal token '{token}' in the card description. "
        f"Create meaningful objectives, technical details, and acceptance criteria. "
        f"The card should feel like it's part of an ongoing project. "
        f"Suggest 2-3 relevant labels (e.g., 'Bug', 'Feature', 'Backend', 'Frontend')."
    )

    # Generate structured card data
    card = await llm.generate_structured(TrelloCard, instruction)

    # Ensure token is in the task
    card.spec.token = token

    # Build description from content
    description_parts = [
        f"## Description\n\n{card.content.description}",
        f"\n**Verification Token**: {token}",
        "\n### Objectives:",
    ]

    # Add objectives as bullet points
    for obj in card.content.objectives:
        description_parts.append(f"- {obj}")

    description_parts.extend(
        [
            f"\n### Technical Details\n\n{card.content.technical_details}",
            "\n### Acceptance Criteria:",
        ]
    )

    # Add acceptance criteria as checklist
    for criteria in card.content.acceptance_criteria:
        description_parts.append(f"- [ ] {criteria}")

    # Add priority
    description_parts.append(f"\n**Priority**: {card.spec.priority.title()}")

    description = "\n".join(description_parts)

    # Ensure token appears in description
    if token not in description:
        description += f"\n\n**Debug Token**: {token}"

    return card.spec.title, description, card.spec.labels


async def generate_trello_checklist(model: str, token: str) -> Dict[str, Any]:
    """Generate checklist content for Trello testing using LLM.

    Args:
        model: The LLM model to use
        token: A unique token to embed in the content for verification

    Returns:
        Dict with checklist name and items
    """
    llm = LLMClient(model_override=model)

    instruction = (
        f"Generate a realistic checklist for a Trello card in a software project. "
        f"You MUST include the literal token '{token}' in the checklist name or first item. "
        f"Create 3-5 actionable checklist items that developers would actually use. "
        f"Some items can be checked, others unchecked."
    )

    checklist = await llm.generate_structured(TrelloChecklistContent, instruction)

    # Ensure token is in the checklist name
    checklist_name = checklist.name
    if token not in checklist_name:
        checklist_name = f"{checklist_name} [{token}]"

    return {
        "name": checklist_name,
        "items": [
            {"name": item.name, "checked": item.checked} for item in checklist.items
        ],
    }
