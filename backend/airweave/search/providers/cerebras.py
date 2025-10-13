"""Cerebras provider implementation.

Supports text generation and structured output.
Does not support embeddings or reranking.
"""

import json
from typing import Any, Dict, List, Optional

from cerebras.cloud.sdk import Cerebras
from pydantic import BaseModel
from tiktoken import Encoding

from airweave.api.context import ApiContext

from ._base import BaseProvider
from .schemas import ProviderModelSpec


class CerebrasProvider(BaseProvider):
    """Cerebras LLM provider."""

    MAX_COMPLETION_TOKENS = 10000
    MAX_STRUCTURED_OUTPUT_TOKENS = 2000

    def __init__(self, api_key: str, model_spec: ProviderModelSpec, ctx: ApiContext) -> None:
        """Initialize Cerebras provider with model specs from defaults.yml."""
        super().__init__(api_key, model_spec, ctx)

        try:
            self.client = Cerebras(api_key=api_key)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Cerebras client: {e}") from e

        self.ctx.logger.debug(f"[CerebrasProvider] Initialized with model spec: {model_spec}")

        self.llm_tokenizer: Optional[Encoding] = None

        if model_spec.llm_model:
            self.llm_tokenizer = self._load_tokenizer(model_spec.llm_model.tokenizer, "llm")

    async def generate(self, messages: List[Dict[str, str]]) -> str:
        """Generate text completion using Cerebras."""
        if not self.model_spec.llm_model:
            raise RuntimeError("LLM model not configured for Cerebras provider")

        if not messages:
            raise ValueError("Cannot generate completion with empty messages")

        try:
            response = self.client.chat.completions.create(
                model=self.model_spec.llm_model.name,
                messages=messages,
                max_completion_tokens=self.MAX_COMPLETION_TOKENS,
            )
        except Exception as e:
            raise RuntimeError(f"Cerebras completion API call failed: {e}") from e

        # Extract content from response
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Cerebras returned empty completion content")

        return content

    async def structured_output(
        self, messages: List[Dict[str, str]], schema: type[BaseModel]
    ) -> BaseModel:
        """Generate structured output using Cerebras JSON schema mode."""
        if not self.model_spec.llm_model:
            raise RuntimeError("LLM model not configured for Cerebras provider")

        if not messages:
            raise ValueError("Cannot generate structured output with empty messages")

        if not schema:
            raise ValueError("Schema is required for structured output")

        try:
            response = self.client.chat.completions.create(
                model=self.model_spec.llm_model.name,
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__.lower(),
                        "strict": True,
                        "schema": schema.model_json_schema(),
                    },
                },
                max_completion_tokens=self.MAX_STRUCTURED_OUTPUT_TOKENS,
            )
        except Exception as e:
            raise RuntimeError(f"Cerebras structured output API call failed: {e}") from e

        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("Cerebras returned empty structured output content")

        try:
            parsed = schema.model_validate(json.loads(content))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Cerebras returned invalid JSON: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to parse Cerebras structured output: {e}") from e

        return parsed

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Not supported by Cerebras."""
        raise NotImplementedError("Cerebras does not support embeddings")

    async def rerank(self, query: str, documents: List[str], top_n: int) -> List[Dict[str, Any]]:
        """Not supported by Cerebras."""
        raise NotImplementedError("Cerebras does not support reranking")
