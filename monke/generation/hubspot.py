from monke.client.llm import LLMClient
from monke.generation.schemas.hubspot import HubSpotContact


async def generate_hubspot_contact(model: str, token: str) -> HubSpotContact:
    """
    Generate a realistic CRM contact with embedded token for verification.
    Token will be added to company field for reliable vector search.
    """
    llm = LLMClient(model_override=model)
    instruction = (
        "Generate a realistic CRM contact for a B2B SaaS context. "
        f"The email should be '{token}@monke-test.com'. "
        "Include realistic firstname, lastname, company name, and other contact details. "
        "Make it look like a real business contact."
    )
    contact = await llm.generate_structured(HubSpotContact, instruction)

    # Ensure invariants
    contact.token = token
    if token not in contact.email:
        # Force tokenized email (stable id)
        contact.email = f"{token}@monke-test.com"

    return contact
