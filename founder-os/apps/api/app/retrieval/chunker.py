"""
Founder OS — Text Chunker
============================
Token-aware document splitting for embedding and retrieval.

Strategies:
  - **Recursive** (default): splits on paragraph → sentence → word boundaries
  - **Sliding window**: overlapping fixed-size chunks for dense coverage
  - **Semantic**: groups sentences by topic coherence (future)

Uses tiktoken for accurate token counting (cl100k_base — same tokenizer
used by OpenAI embeddings and most modern LLMs).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

import tiktoken

# Lazy-loaded encoding (tiktoken downloads BPE data on first call)
_ENCODING: tiktoken.Encoding | None = None


def _get_encoding() -> tiktoken.Encoding:
    global _ENCODING
    if _ENCODING is None:
        _ENCODING = tiktoken.get_encoding("cl100k_base")
    return _ENCODING


@dataclass
class Chunk:
    """A chunk of text from a document, ready for embedding."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    text: str = ""
    index: int = 0              # position in the original document
    token_count: int = 0
    metadata: dict = field(default_factory=dict)  # source_id, title, section, etc.

    def __post_init__(self):
        if not self.token_count and self.text:
            self.token_count = len(_get_encoding().encode(self.text))


def count_tokens(text: str) -> int:
    """Count tokens using the cl100k_base tokenizer."""
    return len(_get_encoding().encode(text))


class TextChunker:
    """
    Token-aware recursive text chunker.

    Splits documents into chunks that fit within embedding model context windows.
    Preserves semantic coherence by splitting at natural boundaries:
      1. Double newlines (paragraph breaks)
      2. Single newlines
      3. Sentences (. ! ?)
      4. Commas / semicolons
      5. Spaces (last resort)

    Args:
        chunk_size: Target tokens per chunk (default: 512)
        chunk_overlap: Overlap tokens between adjacent chunks (default: 50)
        min_chunk_size: Minimum tokens to form a chunk (default: 30)
    """

    # Split hierarchy: most semantic → least semantic
    SEPARATORS = [
        "\n\n",          # paragraph break
        "\n",            # line break
        ". ",            # sentence end
        "! ",            # exclamation
        "? ",            # question
        "; ",            # semicolon
        ", ",            # comma
        " ",             # space
    ]

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        min_chunk_size: int = 30,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

    def chunk_text(
        self,
        text: str,
        metadata: Optional[dict] = None,
    ) -> list[Chunk]:
        """
        Split text into token-aware chunks with overlap.

        Args:
            text: The full document text.
            metadata: Optional metadata to attach to each chunk.

        Returns:
            List of Chunk objects, each within the token limit.
        """
        if not text or not text.strip():
            return []

        # Clean up excessive whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()

        # If the text fits in one chunk, return as-is
        total_tokens = count_tokens(text)
        if total_tokens <= self.chunk_size:
            return [Chunk(
                text=text,
                index=0,
                token_count=total_tokens,
                metadata=metadata or {},
            )]

        # Recursive split
        raw_splits = self._recursive_split(text, self.SEPARATORS)

        # Merge splits into chunks with overlap
        chunks = self._merge_with_overlap(raw_splits, metadata or {})

        return chunks

    def _recursive_split(self, text: str, separators: list[str]) -> list[str]:
        """Recursively split text at the most semantic boundary that fits."""
        if not separators:
            # Last resort: hard split by tokens
            return self._hard_split(text)

        sep = separators[0]
        remaining_seps = separators[1:]

        # Split on the current separator
        parts = text.split(sep) if sep else [text]

        results: list[str] = []
        for part in parts:
            part = part.strip()
            if not part:
                continue

            tokens = count_tokens(part)
            if tokens <= self.chunk_size:
                # Piece fits, keep it
                results.append(part)
            else:
                # Piece is too big, split it further
                sub_parts = self._recursive_split(part, remaining_seps)
                results.extend(sub_parts)

        return results

    def _hard_split(self, text: str) -> list[str]:
        """Hard-split by tokens when no separator works."""
        enc = _get_encoding()
        tokens = enc.encode(text)
        parts: list[str] = []
        for i in range(0, len(tokens), self.chunk_size):
            chunk_tokens = tokens[i:i + self.chunk_size]
            chunk_text = enc.decode(chunk_tokens)
            if chunk_text.strip():
                parts.append(chunk_text.strip())
        return parts

    def _merge_with_overlap(
        self,
        splits: list[str],
        metadata: dict,
    ) -> list[Chunk]:
        """
        Merge small splits into chunks up to chunk_size,
        with chunk_overlap tokens of overlap between consecutive chunks.
        """
        chunks: list[Chunk] = []
        current_parts: list[str] = []
        current_tokens = 0

        for split in splits:
            split_tokens = count_tokens(split)

            # If adding this split would exceed the limit, flush current chunk
            if current_tokens + split_tokens > self.chunk_size and current_parts:
                chunk_text = " ".join(current_parts)
                chunk_token_count = count_tokens(chunk_text)

                if chunk_token_count >= self.min_chunk_size:
                    chunks.append(Chunk(
                        text=chunk_text,
                        index=len(chunks),
                        token_count=chunk_token_count,
                        metadata=dict(metadata),
                    ))

                # Keep overlap: retain the last N tokens worth of parts
                current_parts, current_tokens = self._keep_overlap(current_parts)

            current_parts.append(split)
            current_tokens += split_tokens

        # Flush remaining
        if current_parts:
            chunk_text = " ".join(current_parts)
            chunk_token_count = count_tokens(chunk_text)
            if chunk_token_count >= self.min_chunk_size:
                chunks.append(Chunk(
                    text=chunk_text,
                    index=len(chunks),
                    token_count=chunk_token_count,
                    metadata=dict(metadata),
                ))

        return chunks

    def _keep_overlap(self, parts: list[str]) -> tuple[list[str], int]:
        """Keep the last `chunk_overlap` tokens worth of parts for overlap."""
        if self.chunk_overlap <= 0:
            return [], 0

        overlap_parts: list[str] = []
        overlap_tokens = 0

        for part in reversed(parts):
            part_tokens = count_tokens(part)
            if overlap_tokens + part_tokens > self.chunk_overlap:
                break
            overlap_parts.insert(0, part)
            overlap_tokens += part_tokens

        return overlap_parts, overlap_tokens

    def chunk_documents(
        self,
        documents: list[dict],
    ) -> list[Chunk]:
        """
        Chunk multiple documents at once.

        Each document dict should have:
          - "content" (str): the text to chunk
          - "metadata" (dict, optional): metadata for all chunks from this doc

        Returns all chunks across all documents.
        """
        all_chunks: list[Chunk] = []
        for doc in documents:
            content = doc.get("content", "")
            meta = doc.get("metadata", {})
            chunks = self.chunk_text(content, metadata=meta)
            all_chunks.extend(chunks)
        return all_chunks
