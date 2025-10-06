"""Base provider for LLM operations."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from tiktoken import Encoding, get_encoding

from .schemas import ProviderModelSpec


class BaseProvider(ABC):
    """Base class for LLM providers."""

    def __init__(self, api_key: str, model_spec: ProviderModelSpec) -> None:
        """Initialize provider with API key and model specifications."""
        self.api_key = api_key
        self.model_spec = model_spec

    def _load_tokenizer(self, tokenizer_name: str, model_type: str) -> Optional[Encoding]:
        """Load a tokenizer by name with consistent error handling."""
        try:
            return get_encoding(tokenizer_name)
        except Exception as e:
            raise RuntimeError(
                f"Failed to load {model_type} tokenizer '{tokenizer_name}': {e}"
            ) from e

    def count_tokens(self, text: str, tokenizer: Optional[Encoding]) -> int:
        """Count tokens in text using a specific tokenizer."""
        if tokenizer is None:
            raise RuntimeError("Tokenizer not initialized for token counting")
        if text is None:
            return 0
        return len(tokenizer.encode(text))

    @abstractmethod
    async def generate(self, messages: List[Dict[str, str]]) -> str:
        """Generate text completion."""
        pass

    @abstractmethod
    async def structured_output(
        self, messages: List[Dict[str, str]], schema: type[BaseModel]
    ) -> BaseModel:
        """Generate structured output conforming to Pydantic schema."""
        pass

    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for text."""
        pass

    @abstractmethod
    async def rerank(self, query: str, documents: List[str], top_n: int) -> List[Dict[str, Any]]:
        """Rerank documents by relevance to query."""
        pass
