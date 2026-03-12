"""
Application startup utilities for initializing the parent document store.
Call this once at application startup to ensure optimal performance.
"""

import asyncio

from ai.file_services.vector_utils.parent_store import (
    get_async_parent_retriever_instance,
)


async def initialize_parent_store():
    """
    Initialize the parent document store connection pool.
    Call this once at application startup for optimal performance.
    """
    retriever = get_async_parent_retriever_instance()
    await retriever._ensure_pool()
    print("✅ Parent document store initialized successfully")


def initialize_parent_store_sync():
    """
    Synchronous wrapper for initializing the parent document store.
    Call this once at application startup.
    """
    try:
        asyncio.run(initialize_parent_store())
    except Exception as e:
        print(f"❌ Failed to initialize parent document store: {e}")
        raise


# For FastAPI applications
async def startup_event():
    """
    FastAPI startup event handler.
    Add this to your FastAPI app:

    @app.on_event("startup")
    async def startup():
        await startup_event()
    """
    await initialize_parent_store()


# For graceful shutdown
async def shutdown_event():
    """
    FastAPI shutdown event handler.
    Add this to your FastAPI app:

    @app.on_event("shutdown")
    async def shutdown():
        await shutdown_event()
    """
    retriever = get_async_parent_retriever_instance()
    await retriever.close()
    print("✅ Parent document store closed gracefully")
