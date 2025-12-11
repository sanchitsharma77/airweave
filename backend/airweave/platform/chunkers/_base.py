"""Base chunker interface for all chunker implementations."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Sequence, Union

from chonkie.tokenizer import Tokenizer as ChonkieTokenizer


class TiktokenWrapperForChonkie(ChonkieTokenizer):
    """Wrapper for tiktoken Encoding that allows special tokens.

    Chonkie's AutoTokenizer wraps tiktoken but doesn't pass allowed_special="all"
    when encoding. This causes failures when text contains special tokens like
    <|endoftext|> (common in AI-generated code or discussions about LLMs).

    By inheriting from Chonkie's Tokenizer base class, AutoTokenizer will detect
    this wrapper as "chonkie" backend and call our encode() method directly,
    which properly handles special tokens with allowed_special="all".
    """

    def __init__(self, tiktoken_encoding):
        """Initialize with a tiktoken Encoding object.

        Args:
            tiktoken_encoding: A tiktoken.Encoding instance (e.g., cl100k_base)
        """
        # Initialize Chonkie's Tokenizer base class (sets up vocab/token2id)
        super().__init__()
        self._encoding = tiktoken_encoding

    def __repr__(self) -> str:
        """Return a string representation of the tokenizer."""
        return f"TiktokenWrapperForChonkie(encoding={self._encoding.name})"

    def encode(self, text: str) -> Sequence[int]:
        """Encode text to token IDs, allowing all special tokens.

        Args:
            text: The text to encode

        Returns:
            Sequence of token IDs
        """
        return self._encoding.encode(text, allowed_special="all")

    def decode(self, tokens: Sequence[int]) -> str:
        """Decode token IDs back to text.

        Args:
            tokens: Sequence of token IDs

        Returns:
            Decoded text string
        """
        return self._encoding.decode(list(tokens))

    def tokenize(self, text: str) -> Sequence[Union[str, int]]:
        """Tokenize text into token IDs.

        Args:
            text: The text to tokenize

        Returns:
            Sequence of token IDs
        """
        return self.encode(text)

    def count_tokens(self, text: str) -> int:
        """Count the number of tokens in text.

        Args:
            text: The text to count tokens in

        Returns:
            Number of tokens
        """
        return len(self.encode(text))


class BaseChunker(ABC):
    """Interface for all chunker implementations.

    Chunkers must implement async batch processing for compatibility
    with entity pipeline's concurrent worker model.
    """

    @abstractmethod
    async def chunk_batch(self, texts: List[str]) -> List[List[Dict[str, Any]]]:
        """Chunk a batch of texts asynchronously.

        Args:
            texts: List of textual representations to chunk

        Returns:
            List of chunk lists, where each chunk dict contains:
            {
                "text": str,           # Chunk text content
                "start_index": int,    # Start position in original text
                "end_index": int,      # End position in original text
                "token_count": int     # Number of tokens (cl100k_base tokenizer)
            }

        Raises:
            SyncFailureError: If critical system error occurs (model loading, etc.)
        """
        pass
