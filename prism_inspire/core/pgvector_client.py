"""
pgvector Client — drop-in replacement for milvus_client.py.

Queries the existing `document_chunks` table in Aurora PostgreSQL (pgvector)
that the Agent Engine already populates. Uses asyncpg for async DB access
and OpenAI text-embedding-3-small for query embeddings.

The API mirrors _MilvusClient so callers using milvus_client.get_store()
and vector_store.similarity_search() can switch with minimal changes.

Usage:
    from prism_inspire.core.pgvector_client import pgvector_client

    store = pgvector_client.get_store()
    docs = await store.similarity_search("query text", k=4)
    await store.add_documents([Document(page_content="...", metadata={...})])
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

import asyncpg

from langchain_core.documents import Document

from prism_inspire.core.config import settings
from prism_inspire.core.embedding_client_openai import (
    generate_embedding,
    generate_embeddings_batch,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Text chunking (matches Agent Engine's EmbeddingService.chunk_text)
# ---------------------------------------------------------------------------
CHUNK_SIZE = 1000       # characters per chunk
CHUNK_OVERLAP = 200     # overlap between chunks


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Split text into sentence-boundary-aware chunks."""
    if not text or len(text) <= chunk_size:
        return [text] if text else []
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            chunks.append(text[start:].strip())
            break
        chunk = text[start:end]
        for sep in [". ", ".\n", "! ", "? ", "\n\n"]:
            last_break = chunk.rfind(sep)
            if last_break > chunk_size * 0.5:
                end = start + last_break + len(sep)
                break
        chunks.append(text[start:end].strip())
        start = end - overlap
    return [c for c in chunks if c]


# ---------------------------------------------------------------------------
# Connection pool (lazy singleton)
# ---------------------------------------------------------------------------
_pool: Optional[asyncpg.Pool] = None


async def _get_pool() -> asyncpg.Pool:
    """Return (and lazily create) the asyncpg connection pool.

    Uses VECTOR_PG_DATABASE_URL from settings — this is the Aurora endpoint
    via RDS Proxy that both the monolith and Agent Engine share.
    """
    global _pool
    if _pool is None or _pool._closed:
        db_url = settings.VECTOR_PG_DATABASE_URL
        if not db_url:
            raise RuntimeError(
                "VECTOR_PG_DATABASE_URL is not set — cannot connect to pgvector"
            )
        # asyncpg expects postgresql:// not postgres://
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        _pool = await asyncpg.create_pool(
            dsn=db_url,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        logger.info("pgvector asyncpg pool created successfully")
    return _pool


async def close_pool() -> None:
    """Close the connection pool (call on app shutdown)."""
    global _pool
    if _pool is not None and not _pool._closed:
        await _pool.close()
        _pool = None
        logger.info("pgvector asyncpg pool closed")


# ---------------------------------------------------------------------------
# PgVectorStore — API-compatible with Milvus vector store
# ---------------------------------------------------------------------------

class PgVectorStore:
    """Drop-in replacement for the LangChain Milvus vector store.

    Provides the same ``similarity_search()`` and ``add_documents()`` methods
    so existing agent code can call ``vector_store.similarity_search(query, k)``
    without changes.

    Internally queries the ``document_chunks`` table using pgvector cosine
    distance (``<=>`` operator) and returns LangChain ``Document`` objects.
    """

    def __init__(self, collection_name: Optional[str] = None) -> None:
        """Initialize the store.

        Args:
            collection_name: Ignored for pgvector (kept for Milvus API compat).
                             All data lives in the ``document_chunks`` table.
        """
        self._collection_name = collection_name
        logger.info(
            "PgVectorStore initialized (collection_name=%s — mapped to document_chunks)",
            collection_name,
        )

    # ------------------------------------------------------------------
    # similarity_search — main search entry point
    # ------------------------------------------------------------------
    async def similarity_search(
        self,
        query: str,
        k: int = 4,
        filter: Optional[Dict[str, Any]] = None,
        expr: Optional[str] = None,
        **kwargs: Any,
    ) -> List[Document]:
        """Search for documents similar to the query string.

        Generates an OpenAI embedding for the query, then runs a cosine
        distance search against document_chunks in pgvector.

        Args:
            query: Natural-language query string.
            k: Number of results to return.
            filter: Optional metadata filter dict (e.g. {"file_id": "abc"}).
                    Supports ``file_id`` (single) and ``file_ids`` (list).
            expr: Milvus-style filter expression (parsed for file_id filters).
            **kwargs: Absorbed for Milvus API compatibility.

        Returns:
            List of LangChain Document objects with page_content and metadata.
        """
        # Generate query embedding
        query_embedding = await generate_embedding(query)
        if query_embedding is None:
            logger.warning("Failed to generate embedding for query — returning empty")
            return []

        pool = await _get_pool()
        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        # Build WHERE clauses from filter dict or Milvus expr
        where_clauses = [
            "d.is_active = true",
            "dc.embedding IS NOT NULL",
            "1 - (dc.embedding <=> $1::vector) > 0.25",
        ]
        params: List[Any] = [embedding_str, k]

        file_id_filter = _extract_file_ids(filter, expr)
        if file_id_filter:
            if len(file_id_filter) == 1:
                params.append(file_id_filter[0])
                where_clauses.append(f"d.id = ${len(params)}::uuid")
            else:
                params.append(file_id_filter)
                where_clauses.append(f"d.id = ANY(${len(params)}::uuid[])")

        where_sql = " AND ".join(where_clauses)

        sql = f"""
            SELECT dc.chunk_text,
                   dc.chunk_index,
                   d.id        AS document_id,
                   d.filename,
                   d.file_type,
                   1 - (dc.embedding <=> $1::vector) AS similarity,
                   COALESCE(dc.feedback_weight, 1.0)  AS feedback_weight
            FROM document_chunks dc
            JOIN documents d ON dc.document_id = d.id
            WHERE {where_sql}
            ORDER BY (dc.embedding <=> $1::vector) / COALESCE(dc.feedback_weight, 1.0)
            LIMIT $2
        """

        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(sql, *params)

            documents: List[Document] = []
            for row in rows:
                doc = Document(
                    page_content=row["chunk_text"],
                    metadata={
                        "document_id": str(row["document_id"]),
                        "file_id": str(row["document_id"]),  # compat alias
                        "filename": row["filename"],
                        "file_type": row.get("file_type", ""),
                        "chunk_index": row["chunk_index"],
                        "similarity": float(row["similarity"]),
                        "feedback_weight": float(row["feedback_weight"]),
                        "source": row.get("filename", "pgvector"),
                    },
                )
                documents.append(doc)

            logger.info(
                "pgvector search returned %d results for query (k=%d)",
                len(documents),
                k,
            )
            return documents

        except Exception as e:
            logger.error("pgvector similarity_search failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # add_documents — embed and store documents
    # ------------------------------------------------------------------
    async def add_documents(
        self,
        documents: List[Document],
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """Chunk, embed, and store documents in the document_chunks table.

        Args:
            documents: List of LangChain Document objects with page_content
                       and metadata (must include ``document_id``).
            ids: Optional list of document IDs. If not provided, extracted
                 from each document's metadata["document_id"].

        Returns:
            List of document IDs that were stored.
        """
        pool = await _get_pool()
        stored_ids: List[str] = []

        for i, doc in enumerate(documents):
            doc_id_str = (ids[i] if ids and i < len(ids) else None) or doc.metadata.get(
                "document_id"
            )
            if not doc_id_str:
                doc_id_str = str(uuid.uuid4())

            try:
                doc_uuid = uuid.UUID(doc_id_str) if isinstance(doc_id_str, str) else doc_id_str
            except ValueError:
                doc_uuid = uuid.uuid4()
                doc_id_str = str(doc_uuid)

            text = doc.page_content
            if not text or len(text.strip()) < 10:
                continue

            chunks = _chunk_text(text)
            if not chunks:
                continue

            embeddings = await generate_embeddings_batch(chunks)
            if not embeddings:
                logger.error("Failed to generate embeddings for document %s", doc_id_str)
                continue

            try:
                async with pool.acquire() as conn:
                    # Clear existing chunks for this document
                    await conn.execute(
                        "DELETE FROM document_chunks WHERE document_id = $1",
                        doc_uuid,
                    )

                    for chunk_idx, (chunk_text, embedding) in enumerate(
                        zip(chunks, embeddings)
                    ):
                        embedding_str = (
                            "[" + ",".join(str(v) for v in embedding) + "]"
                        )
                        token_count = len(chunk_text) // 4
                        await conn.execute(
                            """
                            INSERT INTO document_chunks
                                (document_id, chunk_index, chunk_text, embedding, token_count, feedback_weight)
                            VALUES ($1, $2, $3, $4::vector, $5, 1.0)
                            ON CONFLICT (document_id, chunk_index)
                            DO UPDATE SET chunk_text = $3, embedding = $4::vector, token_count = $5
                            """,
                            doc_uuid,
                            chunk_idx,
                            chunk_text,
                            embedding_str,
                            token_count,
                        )

                stored_ids.append(doc_id_str)
                logger.info(
                    "Stored %d chunks for document %s", len(chunks), doc_id_str
                )
            except Exception as e:
                logger.error(
                    "Failed to store chunks for document %s: %s", doc_id_str, e
                )

        return stored_ids


# ---------------------------------------------------------------------------
# Helper: extract file_id filters from Milvus-style filter dict/expr
# ---------------------------------------------------------------------------

def _extract_file_ids(
    filter_dict: Optional[Dict[str, Any]], expr: Optional[str]
) -> Optional[List[str]]:
    """Parse file ID filters from either a dict or a Milvus expression string.

    Supports:
        filter={"file_id": "abc-123"}
        filter={"file_ids": ["abc", "def"]}
        expr='file_id == "abc-123"'
        expr='file_id in ["abc", "def"]'

    Returns a list of UUID strings, or None if no filter.
    """
    ids: List[str] = []

    if filter_dict:
        if "file_id" in filter_dict:
            val = filter_dict["file_id"]
            ids = [val] if isinstance(val, str) else list(val)
        elif "file_ids" in filter_dict:
            ids = list(filter_dict["file_ids"])

    if not ids and expr:
        import re

        # Match: file_id == "uuid"
        single = re.search(r'file_id\s*==\s*"([^"]+)"', expr)
        if single:
            ids = [single.group(1)]
        else:
            # Match: file_id in ["uuid1", "uuid2"]
            multi = re.search(r'file_id\s+in\s*\[([^\]]+)\]', expr)
            if multi:
                ids = re.findall(r'"([^"]+)"', multi.group(1))

    return ids if ids else None


# ---------------------------------------------------------------------------
# _PgVectorClient — singleton matching _MilvusClient interface
# ---------------------------------------------------------------------------

class _PgVectorClient:
    """Singleton pgvector client matching the _MilvusClient interface.

    Usage:
        from prism_inspire.core.pgvector_client import pgvector_client

        store = pgvector_client.get_store()
        docs = await store.similarity_search("query", k=4)
    """

    def __init__(self) -> None:
        self._initialized = True
        logger.info("PgVector client initialized (uses document_chunks table)")

    def get_store(self, collection_name: Optional[str] = None) -> PgVectorStore:
        """Return a PgVectorStore instance.

        Args:
            collection_name: Passed through for API compatibility with
                             _MilvusClient.get_store(). All data lives in
                             the shared ``document_chunks`` table.

        Returns:
            PgVectorStore instance ready for similarity_search() calls.
        """
        return PgVectorStore(collection_name=collection_name)


# Module-level singleton — mirrors ``milvus_client`` in milvus_client.py
pgvector_client = _PgVectorClient()
