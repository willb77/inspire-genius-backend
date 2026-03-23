#!/usr/bin/env python3
"""
Test script for vector store functions: create_a_vector_store and delete_docs_by_file_id
"""

import os
import sys
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
import json

from isort import file

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from prism_inspire.core.milvus_client import milvus_client
from prism_inspire.core.ai_client import embeddings_client
from ai.file_services.vector_utils.vector_store_func import get_similarity_search_async

async def test_similarity_search():
    """
    Test the similarity search with a specific filter expression.
    """
    # Initialize the Milvus vector store using the client
    vector_store = milvus_client.get_store(collection_name="users_db")

    # Test data
    user_id = "c4b8a408-6041-70c8-5746-6586fcf343ab"
    file_id = "d2aa9fbf-92eb-472d-b525-177d69f9d540"
    file_ids_str = f'"{file_id}"'  # Wrap in quotes for the filter expression

    # Construct the filter expression
    filter_expr = f'user_id == "{user_id}" and file_id in [{file_ids_str}]'

    # Perform the search
    query = "test query"
    results = await get_similarity_search_async(
        vector_store=vector_store,
        query=query,
        k=3,
        source=True,
        filter=filter_expr
    )

    print("Search Results:")
    print(results)

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_similarity_search())