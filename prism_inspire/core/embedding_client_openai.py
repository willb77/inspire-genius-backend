"""
OpenAI Embedding Client — drop-in replacement for Google embeddings.

Uses OpenAI text-embedding-3-small (1536 dimensions) via the AsyncOpenAI SDK
that's already a project dependency. This replaces embeddings_client_google
from ai_client.py for pgvector search in the monolith.

Usage:
    from prism_inspire.core.embedding_client_openai import (
        generate_embedding,
        generate_embeddings_batch,
    )

    embedding = await generate_embedding("search query")
    embeddings = await generate_embeddings_batch(["text1", "text2"])
"""
from __future__ import annotations

import logging
from typing import List, Optional

from openai import AsyncOpenAI

from prism_inspire.core.config import settings

logger = logging.getLogger(__name__)

# Singleton client — reuses connection pool across calls
_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

MODEL = "text-embedding-3-small"
DIMENSIONS = 1536
MAX_BATCH_SIZE = 100  # OpenAI batch limit
MAX_INPUT_LENGTH = 8000  # characters per text input


async def generate_embedding(text: str) -> Optional[List[float]]:
    """Generate a single embedding via OpenAI text-embedding-3-small.

    Args:
        text: Input text to embed. Truncated to 8000 characters.

    Returns:
        List of 1536 floats, or None on failure.
    """
    if not text or not text.strip():
        return None
    try:
        response = await _client.embeddings.create(
            model=MODEL,
            input=text[:MAX_INPUT_LENGTH],
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error("OpenAI embedding generation failed: %s", e)
        return None


async def generate_embeddings_batch(
    texts: List[str],
) -> Optional[List[List[float]]]:
    """Generate embeddings for a batch of texts.

    Splits into sub-batches of MAX_BATCH_SIZE to respect OpenAI limits.

    Args:
        texts: List of input texts. Each truncated to 8000 characters.

    Returns:
        List of embedding vectors (same order as input), or None on failure.
    """
    if not texts:
        return None

    all_embeddings: List[List[float]] = []

    for batch_start in range(0, len(texts), MAX_BATCH_SIZE):
        batch = texts[batch_start : batch_start + MAX_BATCH_SIZE]
        truncated = [t[:MAX_INPUT_LENGTH] for t in batch]
        try:
            response = await _client.embeddings.create(
                model=MODEL,
                input=truncated,
            )
            # Sort by index to guarantee order matches input
            sorted_data = sorted(response.data, key=lambda x: x.index)
            all_embeddings.extend([item.embedding for item in sorted_data])
        except Exception as e:
            logger.error(
                "OpenAI batch embedding failed (batch %d-%d): %s",
                batch_start,
                batch_start + len(batch),
                e,
            )
            return None

    return all_embeddings
