from typing import Optional
from langchain_milvus import Milvus
from pymilvus import connections, MilvusClient as PyMilvusClient
from prism_inspire.core.config import settings
from prism_inspire.core.log_config import logger
from prism_inspire.core.ai_client import embeddings_client_google


def _ensure_orm_connection(uri: str, token: str) -> None:
    """Ensure the pymilvus ORM connections registry has an active connection.

    langchain-milvus 0.3.x internally creates a ``MilvusClient`` whose gRPC
    handler is registered under a random alias (``cm-<id>``).  The pymilvus
    ORM ``Collection`` class later looks up that alias via
    ``connections._fetch_handler`` — but in pymilvus 2.6.x the MilvusClient
    API and ORM connections API use separate registries, so the lookup fails.

    As a workaround we pre-create a ``MilvusClient``, grab its handler, and
    copy it into the ORM registry under the same alias.  We then override
    ``MilvusClient.__init__`` for subsequent calls so that every new instance
    also gets registered.
    """
    _orig_init = PyMilvusClient.__init__

    def _patched_init(self: PyMilvusClient, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        _orig_init(self, *args, **kwargs)
        try:
            alias = self._using
            handler = self._get_connection()
            if hasattr(connections, "_alias_handlers"):
                connections._alias_handlers[alias] = handler
        except Exception:
            pass

    PyMilvusClient.__init__ = _patched_init  # type: ignore[method-assign]


class _MilvusClient:
    """
    A thread-safe singleton client for managing Milvus vector store instances.

    This class ensures that the connection to Milvus and the embedding model
    are initialized only once. It provides a central point of access for
    obtaining vector store instances for different collections.
    """

    def __init__(self) -> None:
        try:
            self._connection_args = {
                "uri": settings.MILVUS_URI,
                "token": settings.MILVUS_PASSWORD or "",
            }
            # Patch MilvusClient so every instance auto-registers in ORM connections
            _ensure_orm_connection(
                settings.MILVUS_URI,
                settings.MILVUS_PASSWORD or "",
            )
            self._embeddings = embeddings_client_google
            self._initialized = True
            logger.info("Milvus client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Milvus client: {e}")
            raise

    def get_store(self, collection_name: Optional[str] = None) -> Milvus:
        """
        Returns a Milvus vector store for the specified collection.
        """
        name = collection_name or settings.MILVUS_COLLECTION_NAME

        try:
            logger.info(f"Retrieving Milvus store for collection: '{name}'")
            store = Milvus(
                embedding_function=self._embeddings,
                connection_args=self._connection_args,
                collection_name=name,
                index_params={"index_type": "HNSW", "metric_type": "L2"},
                drop_old=False,
            )
            logger.info(f"Successfully created Milvus store for collection '{name}'")
            return store
        except Exception as e:
            logger.error(f"Failed to create Milvus store for '{name}': {e}")
            raise


milvus_client = _MilvusClient()
