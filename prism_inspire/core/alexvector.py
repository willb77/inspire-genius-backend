from prism_inspire.core.log_config import logger
from prism_inspire.core.milvus_client import milvus_client
from prism_inspire.core.config import settings



def get_alex_db():
    return milvus_client.get_store(collection_name=settings.MILVUS_COLLECTION_NAME)

def get_coaches_db():
    return milvus_client.get_store(collection_name="other_coaches_db")