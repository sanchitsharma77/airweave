"""Groq provider implementation.

Supports text generation, structured output, and reranking via structured output.
Does not support embeddings.
"""

import json
from typing import Any, Dict, List, Optional

from groq import AsyncGroq
from pydantic import BaseModel
from tiktoken import Encoding, get_encoding

from ._base import BaseProvider
from .schemas import ProviderModelSpec


class GroqProvider(BaseProvider):
    """Groq LLM provider."""

    MAX_COMPLETION_TOKENS = 10000
    MAX_STRUCTURED_OUTPUT_TOKENS = 2000

    def __init__(self, api_key: str, model_spec: ProviderModelSpec) -> None:
        """Initialize Groq provider with model specs from defaults.yml."""
        super().__init__(api_key, model_spec)

        try:
            self.client = AsyncGroq(api_key=api_key)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Groq client: {e}") from e

        self._llm_tokenizer: Optional[Encoding] = None

        if model_spec.llm_model:
            # tokenizer is guaranteed by LLMModelConfig schema validation
            try:
                self._llm_tokenizer = get_encoding(model_spec.llm_model.tokenizer)
            except Exception as e:
                raise RuntimeError(
                    f"Failed to load LLM tokenizer '{model_spec.llm_model.tokenizer}': {e}"
                ) from e

    def count_tokens(self, text: str, model_type: str = "llm") -> int:
        """Count tokens using model-specific tokenizer."""
        if model_type == "llm":
            if not self._llm_tokenizer:
                raise RuntimeError("LLM tokenizer not initialized for token counting")
            return len(self._llm_tokenizer.encode(text))
        else:
            raise ValueError(f"Invalid model_type: {model_type}. Groq only supports 'llm'")

    async def generate(self, messages: List[Dict[str, str]]) -> str:
        """Generate text completion using Groq."""
        if not self.model_spec.llm_model:
            raise RuntimeError("LLM model not configured for Groq provider")

        if not messages:
            raise ValueError("Cannot generate completion with empty messages")

        try:
            response = await self.client.chat.completions.create(
                model=self.model_spec.llm_model.name,
                messages=messages,
                max_completion_tokens=self.MAX_COMPLETION_TOKENS,
            )
        except Exception as e:
            raise RuntimeError(f"Groq completion API call failed: {e}") from e

        content = response.choices[0].message.content
        if not content:
            raise ValueError("Groq returned empty completion content")

        return content

    async def structured_output(
        self, messages: List[Dict[str, str]], schema: type[BaseModel]
    ) -> BaseModel:
        """Generate structured output using Groq JSON schema mode."""
        if not self.model_spec.llm_model:
            raise RuntimeError("LLM model not configured for Groq provider")

        if not messages:
            raise ValueError("Cannot generate structured output with empty messages")

        if not schema:
            raise ValueError("Schema is required for structured output")

        try:
            response = await self.client.chat.completions.create(
                model=self.model_spec.llm_model.name,
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__.lower(),
                        "schema": schema.model_json_schema(),
                    },
                },
                max_completion_tokens=self.MAX_STRUCTURED_OUTPUT_TOKENS,
            )
        except Exception as e:
            raise RuntimeError(f"Groq structured output API call failed: {e}") from e

        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("Groq returned empty structured output content")

        try:
            parsed = schema.model_validate(json.loads(content))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Groq returned invalid JSON: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to parse Groq structured output: {e}") from e

        return parsed

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Not supported by Groq."""
        raise NotImplementedError("Groq does not support embeddings")

    async def rerank(self, query: str, documents: List[str], top_n: int) -> List[Dict[str, Any]]:
        """Rerank documents using Groq structured output."""
        from airweave.search.prompts import RERANKING_SYSTEM_PROMPT

        if not self.model_spec.rerank_model:
            raise RuntimeError("Rerank model not configured for Groq provider")

        if not documents:
            raise ValueError("Cannot rerank empty document list")

        if top_n < 1:
            raise ValueError(f"top_n must be >= 1, got {top_n}")

        # Define schema for reranking
        class RankedResult(BaseModel):
            index: int
            relevance_score: float

        class RerankResult(BaseModel):
            rankings: List[RankedResult]

        # Format documents for prompt
        formatted_docs = "\n\n".join([f"[{i}] {doc}" for i, doc in enumerate(documents)])
        user_prompt = (
            f"Query: {query}\n\nSearch Results:\n{formatted_docs}\n\n"
            "Please rerank these results from most to least relevant to the query."
        )

        rerank_result = await self.structured_output(
            messages=[
                {"role": "system", "content": RERANKING_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            schema=RerankResult,
        )

        if not rerank_result.rankings:
            raise RuntimeError("Groq returned empty rankings")

        return [
            {"index": r.index, "relevance_score": r.relevance_score}
            for r in rerank_result.rankings[:top_n]
        ]
