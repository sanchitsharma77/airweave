"""Airtable content generation adapter.

Generates realistic record content for testing Airtable integration using LLM.
"""

from typing import Dict, List, Tuple

from monke.client.llm import LLMClient
from monke.generation.schemas.airtable import AirtableRecord


async def generate_airtable_record(
    model: str, token: str
) -> Tuple[Dict[str, any], str, List[str]]:
    """Generate record content for Airtable testing using LLM.

    Args:
        model: The LLM model to use
        token: A unique token to embed in the content for verification

    Returns:
        Tuple of (fields_dict, table_name, comments) where:
        - fields_dict contains the field values for the record
        - table_name is the name of the table
        - comments is a list of comment texts to add to the record
    """
    llm = LLMClient(model_override=model)

    instruction = (
        "Generate a realistic Airtable record for a project management table. "
        "The record should be for a task or project item. "
        f"You MUST include the literal token '{token}' in the primary field (name), notes field, "
        f"and in at least one comment. "
        "Make it realistic and professional, like something from a real project tracking system. "
        "Include a meaningful description, status, tags, and 1-2 helpful comments that a "
        "team member might add (e.g., status updates, questions, or clarifications)."
    )

    # Generate structured record data
    record = await llm.generate_structured(AirtableRecord, instruction)

    # Ensure token is in the content
    record.spec.token = token

    # Make sure token appears in primary field and notes
    if token not in record.content.primary_field:
        record.content.primary_field = f"[{token}] {record.content.primary_field}"

    if token not in record.content.notes:
        record.content.notes += f"\n\nTest token: {token}"

    # Ensure token appears in at least one comment
    has_token_in_comment = any(token in comment for comment in record.content.comments)
    if not has_token_in_comment and record.content.comments:
        # Add token to first comment
        record.content.comments[0] = f"{record.content.comments[0]} (Token: {token})"
    elif not record.content.comments:
        # Create a default comment with token
        record.content.comments = [f"Status update - verification token: {token}"]

    # Build the fields dictionary for Airtable API
    fields = {
        "Name": record.content.primary_field,
        "Description": record.content.description,
        "Status": record.content.status,
        "Tags": ", ".join(record.content.tags) if record.content.tags else "",
        "Notes": record.content.notes,
    }

    return fields, record.spec.table_name, record.content.comments
