"""Attio content generation adapter.

Generates realistic CRM content for testing Attio integration using LLM.
"""

from typing import Dict, Tuple

from monke.client.llm import LLMClient
from monke.generation.schemas.attio import AttioCompany, AttioNoteContent, AttioPerson


async def generate_attio_company(model: str, token: str) -> Dict:
    """Generate company record content for Attio testing using LLM.

    Args:
        model: The LLM model to use
        token: A unique token to embed in the content for verification

    Returns:
        Dict with company data ready for Attio API
    """
    llm = LLMClient(model_override=model)

    instruction = (
        "Generate a realistic B2B technology company for a CRM database. "
        "Make it sound like a real SaaS or tech company you might track in a CRM. "
        f"You MUST include the literal token '{token}' in the company description. "
        "Create meaningful categories, products, and notes."
    )

    # Generate structured company data
    company = await llm.generate_structured(AttioCompany, instruction)

    # Ensure token is in the description
    company.spec.token = token
    if token not in company.content.description:
        company.content.description += f"\n\nVerification Token: {token}"

    # Build the full description with all context
    full_description = (
        f"{company.content.description}\n\n"
        f"**Key Products/Services:**\n"
        + "\n".join(f"- {p}" for p in company.content.key_products)
        + f"\n\n**Notes:**\n{company.content.notes}"
    )

    # Make domain unique by incorporating the token to avoid conflicts
    unique_domain = f"{company.spec.domain.split('.')[0]}-{token}.com"

    return {
        "name": f"{company.spec.name} ({token})",  # Make name unique too
        "domain": unique_domain,
        "industry": company.spec.industry,
        "description": full_description,
        "categories": company.content.categories,
        "token": token,
    }


async def generate_attio_person(model: str, token: str) -> Dict:
    """Generate person record content for Attio testing using LLM.

    Args:
        model: The LLM model to use
        token: A unique token to embed in the content for verification

    Returns:
        Dict with person data ready for Attio API
    """
    llm = LLMClient(model_override=model)

    instruction = (
        "Generate a realistic professional person for a CRM database. "
        "Make it sound like a real business contact you might track. "
        f"You MUST include the literal token '{token}' in the person's bio. "
        "Create a believable name, email, title, and professional interests."
    )

    # Generate structured person data
    person = await llm.generate_structured(AttioPerson, instruction)

    # Ensure token is in the bio
    person.spec.token = token
    if token not in person.content.bio:
        person.content.bio += f"\n\nVerification Token: {token}"

    # Build full bio with context
    full_bio = (
        f"{person.content.bio}\n\n"
        f"**Professional Interests:**\n"
        + "\n".join(f"- {i}" for i in person.content.interests)
        + f"\n\n**Notes:**\n{person.content.notes}"
    )

    # Make email unique by incorporating the token to avoid conflicts
    email_parts = person.spec.email.split('@')
    unique_email = f"{email_parts[0]}-{token}@{email_parts[1]}"

    return {
        "first_name": person.spec.first_name,
        "last_name": person.spec.last_name,
        "email": unique_email,
        "title": person.spec.title,
        "bio": full_bio,
        "token": token,
    }


async def generate_attio_note(model: str, token: str) -> Tuple[str, str]:
    """Generate note content for Attio testing using LLM.

    Args:
        model: The LLM model to use
        token: A unique token to embed in the content for verification

    Returns:
        Tuple of (title, content)
    """
    llm = LLMClient(model_override=model)

    instruction = (
        "Generate a realistic CRM note about a business interaction or meeting. "
        "Make it sound like something a sales rep or account manager would write. "
        f"You MUST include the literal token '{token}' in the note content. "
        "Create a clear title and detailed content with key points."
    )

    # Generate structured note data
    note = await llm.generate_structured(AttioNoteContent, instruction)

    # Ensure token is in content
    if token not in note.content:
        note.content += f"\n\nVerification Token: {token}"

    # Build full content
    full_content = (
        f"{note.content}\n\n"
        f"**Key Points:**\n" + "\n".join(f"- {p}" for p in note.key_points)
    )

    return note.title, full_content
