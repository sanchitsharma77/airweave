"""Base provider for LLM operations."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from pydantic import BaseModel

from .schemas import ProviderModelSpec


class BaseProvider(ABC):
    """Base class for LLM providers."""

    def __init__(self, api_key: str, model_spec: ProviderModelSpec) -> None:
        """Initialize provider with API key and model specifications.

        Args:
            api_key: API key for the provider
            model_spec: Complete model specification with llm/embedding/rerank models
        """
        self.api_key = api_key
        self.model_spec = model_spec

    @abstractmethod
    def count_tokens(self, text: str, model_type: str = "llm") -> int:
        """Count tokens in text for this provider's tokenizer.

        Args:
            text: Text to count tokens for
            model_type: Type of model ('llm', 'embedding') to use correct tokenizer

        Returns:
            Number of tokens
        """
        pass

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
