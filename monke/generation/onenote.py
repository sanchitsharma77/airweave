"""OneNote-specific generation adapter: page generator."""

from typing import Tuple

from monke.client.llm import LLMClient
from monke.generation.schemas.onenote import OneNotePage


async def generate_onenote_page(
    model: str, token: str, is_update: bool = False
) -> Tuple[str, str]:
    """
    Returns (title, html_content). The literal token must appear in the content.
    Uses structured generation with JSON mode under the hood.
    """
    llm = LLMClient(model_override=model)

    if is_update:
        instruction = (
            "Create a concise follow-up OneNote page about a (synthetic) project update. "
            f"Include the EXACT literal token '{token}' somewhere in the content. "
            "Return JSON with fields: title (string), content (string with simple HTML)."
        )
    else:
        instruction = (
            "Create a concise (synthetic) OneNote page for a project planning document. "
            f"Include the EXACT literal token '{token}' somewhere in the content. "
            "Return JSON with fields: title (string), content (string with simple HTML)."
        )

    page = await llm.generate_structured(OneNotePage, instruction)

    # Ensure token is in content
    content = page.content
    if token not in content:
        content += f"<p>Reference: {token}</p>"

    return page.title, content
