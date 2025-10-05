"""OpenAI provider implementation.

Supports text generation, structured output, embeddings, and reranking.
Most complete provider with all capabilities.
"""

from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI
from pydantic import BaseModel
from tiktoken import Encoding, get_encoding

from ._base import BaseProvider
from .schemas import ProviderModelSpec


class OpenAIProvider(BaseProvider):
    """OpenAI LLM provider."""

    MAX_COMPLETION_TOKENS = 10000
    MAX_STRUCTURED_OUTPUT_TOKENS = 2000
    MAX_EMBEDDING_BATCH_SIZE = 100

    def __init__(self, api_key: str, model_spec: ProviderModelSpec) -> None:
        """Initialize OpenAI provider with model specs from defaults.yml."""
        super().__init__(api_key, model_spec)

        try:
            self.client = AsyncOpenAI(api_key=api_key, timeout=1200.0, max_retries=2)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize OpenAI client: {e}") from e

        self._llm_tokenizer: Optional[Encoding] = None
        self._embedding_tokenizer: Optional[Encoding] = None

        if model_spec.llm_model:
            # tokenizer is guaranteed by LLMModelConfig schema validation
            try:
                self._llm_tokenizer = get_encoding(model_spec.llm_model.tokenizer)
            except Exception as e:
                raise RuntimeError(
                    f"Failed to load LLM tokenizer '{model_spec.llm_model.tokenizer}': {e}"
                ) from e

        if model_spec.embedding_model:
            # tokenizer is guaranteed by EmbeddingModelConfig schema validation
            try:
                self._embedding_tokenizer = get_encoding(model_spec.embedding_model.tokenizer)
            except Exception as e:
                raise RuntimeError(
                    f"Failed to load embedding tokenizer "
                    f"'{model_spec.embedding_model.tokenizer}': {e}"
                ) from e

    def count_tokens(self, text: str, model_type: str = "llm") -> int:
        """Count tokens using model-specific tokenizer."""
        if model_type == "embedding":
            if not self._embedding_tokenizer:
                raise RuntimeError("Embedding tokenizer not initialized for token counting")
            return len(self._embedding_tokenizer.encode(text))
        elif model_type == "llm":
            if not self._llm_tokenizer:
                raise RuntimeError("LLM tokenizer not initialized for token counting")
            return len(self._llm_tokenizer.encode(text))
        else:
            raise ValueError(f"Invalid model_type: {model_type}. Must be 'llm' or 'embedding'")

    async def generate(self, messages: List[Dict[str, str]]) -> str:
        """Generate text completion using OpenAI."""
        if not self.model_spec.llm_model:
            raise RuntimeError("LLM model not configured for OpenAI provider")

        if not messages:
            raise ValueError("Cannot generate completion with empty messages")

        try:
            response = await self.client.chat.completions.create(
                model=self.model_spec.llm_model.name,
                messages=messages,
                max_completion_tokens=self.MAX_COMPLETION_TOKENS,
            )
        except Exception as e:
            raise RuntimeError(f"OpenAI completion API call failed: {e}") from e

        content = response.choices[0].message.content
        if not content:
            raise ValueError("OpenAI returned empty completion content")

        return content

    async def structured_output(
        self, messages: List[Dict[str, str]], schema: type[BaseModel]
    ) -> BaseModel:
        """Generate structured output using OpenAI Responses API."""
        if not self.model_spec.llm_model:
            raise RuntimeError("LLM model not configured for OpenAI provider")

        if not messages:
            raise ValueError("Cannot generate structured output with empty messages")

        if not schema:
            raise ValueError("Schema is required for structured output")

        try:
            response = await self.client.responses.parse(
                model=self.model_spec.llm_model.name,
                input=messages,
                text_format=schema,
                max_output_tokens=self.MAX_STRUCTURED_OUTPUT_TOKENS,
            )
        except Exception as e:
            raise RuntimeError(f"OpenAI structured output API call failed: {e}") from e

        parsed = response.output_parsed
        if not parsed:
            raise RuntimeError("OpenAI returned empty structured output")

        return parsed

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings with batching and validation."""
        if not self.model_spec.embedding_model:
            raise RuntimeError("Embedding model not configured for OpenAI provider")

        if not texts:
            raise ValueError("Cannot embed empty text list")

        self._validate_embed_inputs(texts)
        return await self._process_embeddings(texts)

    def _validate_embed_inputs(self, texts: List[str]) -> None:
        """Validate texts for embedding."""
        for i, text in enumerate(texts):
            if not text or not text.strip():
                raise ValueError(f"Text at index {i} is empty")

        max_tokens = self.model_spec.embedding_model.max_tokens
        if not max_tokens:
            raise ValueError("Max tokens not configured for embedding model")

        for i, text in enumerate(texts):
            token_count = self.count_tokens(text, model_type="embedding")
            if token_count > max_tokens:
                raise ValueError(
                    f"Text at index {i} has {token_count} tokens, exceeds max of {max_tokens}"
                )

    async def _process_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Process embeddings in batches."""
        all_embeddings = []

        for batch_start in range(0, len(texts), self.MAX_EMBEDDING_BATCH_SIZE):
            batch = texts[batch_start : batch_start + self.MAX_EMBEDDING_BATCH_SIZE]
            batch_result = await self._embed_batch(batch, batch_start)
            all_embeddings.extend(batch_result)

        if len(all_embeddings) != len(texts):
            raise RuntimeError(
                f"Embedding count mismatch: got {len(all_embeddings)} for {len(texts)} texts"
            )

        return all_embeddings

    async def _embed_batch(self, batch: List[str], batch_start: int) -> List[List[float]]:
        """Embed a single batch with validation."""
        try:
            response = await self.client.embeddings.create(
                input=batch,
                model=self.model_spec.embedding_model.name,
            )
        except Exception as e:
            raise RuntimeError(
                f"OpenAI embeddings API call failed at index {batch_start}: {e}"
            ) from e

        if not response.data:
            raise RuntimeError(f"OpenAI returned no embeddings for batch at {batch_start}")

        if len(response.data) != len(batch):
            raise RuntimeError(
                f"OpenAI returned {len(response.data)} embeddings but expected {len(batch)}"
            )

        return [item.embedding for item in response.data]

    async def rerank(self, query: str, documents: List[str], top_n: int) -> List[Dict[str, Any]]:
        """Rerank documents using OpenAI structured output."""
        from airweave.search.prompts import RERANKING_SYSTEM_PROMPT

        if not self.model_spec.rerank_model:
            raise RuntimeError("Rerank model not configured for OpenAI provider")

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
            raise RuntimeError("OpenAI returned empty rankings")

        return [
            {"index": r.index, "relevance_score": r.relevance_score}
            for r in rerank_result.rankings[:top_n]
        ]
