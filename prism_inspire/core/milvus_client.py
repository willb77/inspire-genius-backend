from typing import Optional
from langchain_milvus import Milvus
from pymilvus import connections
from prism_inspire.core.config import settings
from prism_inspire.core.log_config import logger
from prism_inspire.core.ai_client import embeddings_client_google

class _MilvusClient:
    """
    A thread-safe singleton client for managing Milvus vector store instances.

    This class ensures that the connection to Milvus and the embedding model
    are initialized only once. It provides a central point of access for
    obtaining vector store instances for different collections.
    """

    def __init__(self):
        """
        Initializes the connection arguments and embeddings.
        This is designed to be idempotent.
        """

        try:
            self._connection_args = {
                "uri": settings.MILVUS_URI,
                "token": settings.MILVUS_PASSWORD,
            }
            # Establish the pymilvus connection so langchain_milvus can use it
            connections.connect(
                alias="default",
                uri=settings.MILVUS_URI,
                token=settings.MILVUS_PASSWORD or "",
            )
            self._embeddings = embeddings_client_google
            self._initialized = True
            logger.info("Milvus client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Milvus client: {e}")
            raise

    def get_store(self, collection_name: Optional[str] = None) -> Milvus:
        """
        Returns a cached Milvus vector store for the specified collection,
        creating it if it doesn't exist.
        """
        name = collection_name or settings.MILVUS_COLLECTION_NAME
        # this will also create a new collection if not available
            
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
