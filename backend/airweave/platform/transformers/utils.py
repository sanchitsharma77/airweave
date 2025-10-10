"""Utils for transformers."""

import tiktoken

# Max chunk size for embedding models (e.g. OpenAI's text-embedding-ada-002)
# While OpenAI allows up to 8191 tokens per text, we use a safer limit
# to avoid batch processing errors and account for overhead
MAX_CHUNK_SIZE = 7500  # Reduced from 8191 for safer batch processing
MARGIN_OF_ERROR = 250
METADATA_SIZE = 1200

# Cache the encoding at module level to avoid duplicate registration errors
# when called concurrently from multiple async tasks
_ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens using the cl100k_base tokenizer (used by OpenAI's text-embedding models)."""
    return len(_ENCODING.encode(text))
