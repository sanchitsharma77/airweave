from monke.client.llm import LLMClient
from monke.generation.schemas.salesforce import SalesforceContact


async def generate_salesforce_contact(model: str, token: str) -> SalesforceContact:
    """
    Generate a realistic Salesforce contact. The email MUST contain the token (e.g., token@monke.test)
    so we can reliably verify later via search.
    """
    llm = LLMClient(model_override=model)
    instruction = (
        "Generate a realistic B2B contact for Salesforce CRM. "
        f"The literal token '{token}' MUST be embedded in the email local-part (e.g., '{token}@example.test') "
        "and may appear in description or notes. Include plausible contact details."
    )
    contact = await llm.generate_structured(SalesforceContact, instruction)

    # Ensure invariants
    contact.token = token
    if token not in contact.email:
        # Force tokenized email (stable id)
        local = f"{token}.contact"
        contact.email = f"{local}@example.test"

    return contact
