"""Content generators for Pipedrive test entities."""

from monke.client.llm import LLMClient
from monke.generation.schemas.pipedrive import (
    PipedriveActivity,
    PipedriveDeal,
    PipedriveLead,
    PipedriveNote,
    PipedriveOrganization,
    PipedrivePerson,
    PipedriveProduct,
)


async def generate_pipedrive_person(model: str, token: str) -> PipedrivePerson:
    """Generate a realistic CRM person/contact with embedded token for verification.

    Token will be added to the organization name field for reliable vector search.
    """
    llm = LLMClient(model_override=model)
    instruction = (
        "Generate a realistic CRM contact for a B2B sales context. "
        f"The email should be '{token}@monke-test.com'. "
        "Include realistic name, phone, and organization name. "
        "Make it look like a real business contact."
    )
    person = await llm.generate_structured(PipedrivePerson, instruction)

    # Ensure invariants
    person.token = token
    if token not in person.email:
        person.email = f"{token}@monke-test.com"

    # Embed token in org_name for vector search
    if person.org_name:
        person.org_name = f"{person.org_name} [{token}]"
    else:
        person.org_name = f"Monke Test Corp [{token}]"

    return person


async def generate_pipedrive_organization(model: str, token: str) -> PipedriveOrganization:
    """Generate a realistic organization with embedded token for verification."""
    llm = LLMClient(model_override=model)
    instruction = (
        "Generate a realistic company/organization for a B2B CRM context. "
        "Include a company name and business address. "
        "Make it look like a real business."
    )
    org = await llm.generate_structured(PipedriveOrganization, instruction)

    # Ensure invariants - embed token in name
    org.token = token
    org.name = f"{org.name} [{token}]"

    return org


async def generate_pipedrive_deal(model: str, token: str) -> PipedriveDeal:
    """Generate a realistic deal with embedded token for verification."""
    llm = LLMClient(model_override=model)
    instruction = (
        "Generate a realistic sales deal/opportunity for a B2B CRM context. "
        "Include a deal title and value. "
        "Make it look like a real sales opportunity."
    )
    deal = await llm.generate_structured(PipedriveDeal, instruction)

    # Ensure invariants - embed token in title
    deal.token = token
    deal.title = f"{deal.title} [{token}]"

    return deal


async def generate_pipedrive_activity(model: str, token: str) -> PipedriveActivity:
    """Generate a realistic activity with embedded token for verification."""
    llm = LLMClient(model_override=model)
    instruction = (
        "Generate a realistic sales activity for a B2B CRM context. "
        "This could be a follow-up call, meeting, or task. "
        "Include a subject and optional note. "
        "The activity_type should be one of: call, meeting, task, deadline, email, lunch. "
        "Make it look like a real sales activity."
    )
    activity = await llm.generate_structured(PipedriveActivity, instruction)

    # Ensure invariants - embed token in subject
    activity.token = token
    activity.subject = f"{activity.subject} [{token}]"

    # Ensure valid activity type
    valid_types = ["call", "meeting", "task", "deadline", "email", "lunch"]
    if activity.activity_type not in valid_types:
        activity.activity_type = "task"

    return activity


async def generate_pipedrive_product(model: str, token: str) -> PipedriveProduct:
    """Generate a realistic product with embedded token for verification."""
    llm = LLMClient(model_override=model)
    instruction = (
        "Generate a realistic product/service for a B2B sales context. "
        "Include a product name, code/SKU, description, and price. "
        "Make it look like a real product or service offering."
    )
    product = await llm.generate_structured(PipedriveProduct, instruction)

    # Ensure invariants - embed token in name
    product.token = token
    product.name = f"{product.name} [{token}]"

    return product


async def generate_pipedrive_lead(model: str, token: str) -> PipedriveLead:
    """Generate a realistic lead with embedded token for verification."""
    llm = LLMClient(model_override=model)
    instruction = (
        "Generate a realistic sales lead for a B2B CRM context. "
        "Include a lead title and expected value. "
        "Make it look like a real potential sales opportunity."
    )
    lead = await llm.generate_structured(PipedriveLead, instruction)

    # Ensure invariants - embed token in title
    lead.token = token
    lead.title = f"{lead.title} [{token}]"

    return lead


async def generate_pipedrive_note(model: str, token: str) -> PipedriveNote:
    """Generate a realistic note with embedded token for verification."""
    llm = LLMClient(model_override=model)
    instruction = (
        "Generate a realistic CRM note for a B2B sales context. "
        "This could be meeting notes, a follow-up reminder, or customer feedback. "
        "Make the content detailed and look like a real sales note."
    )
    note = await llm.generate_structured(PipedriveNote, instruction)

    # Ensure invariants - embed token in content
    note.token = token
    note.content = f"{note.content}\n\n[Reference: {token}]"

    return note
