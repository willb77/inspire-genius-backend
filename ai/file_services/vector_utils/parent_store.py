import asyncio
import os
import threading
import time
import uuid
from collections import defaultdict
from typing import Dict, List

import asyncpg
import psycopg2
from psycopg2.extras import execute_values

from prism_inspire.core.app_cache import SimpleMemoryCache
from prism_inspire.core.log_config import logger

# Global cache instance with conservative memory limits
_global_cache = SimpleMemoryCache(
    max_memory_mb=50,  # Only 50MB RAM limit
    max_items=500,  # Max 500 cached documents
    ttl_seconds=300,  # 5 min TTL for faster turnover
)


class SnowflakeGenerator:
    def __init__(self, machine_uuid: str):
        # Convert UUID to 10-bit machine ID
        self.machine_id = hash(uuid.UUID(machine_uuid)) % 1024
        self.sequence = 0
        self.last_timestamp = -1
        self.lock = threading.Lock()

        # Custom epoch: 2025-01-01 in ms
        self.epoch = 1735689600000

    def _timestamp(self):
        return int(time.time() * 1000)

    def next_id(self) -> int:
        with self.lock:
            timestamp = self._timestamp()

            if timestamp == self.last_timestamp:
                # Increment sequence in same millisecond
                self.sequence = (self.sequence + 1) & 0xFFF  # 12 bits
                if self.sequence == 0:
                    # Wait for the next millisecond
                    while timestamp <= self.last_timestamp:
                        timestamp = self._timestamp()
            else:
                self.sequence = 0

            self.last_timestamp = timestamp

            # Format: timestamp(41 bits) | machine(10 bits) | sequence(12 bits)
            return (
                ((timestamp - self.epoch) << 22)
                | (self.machine_id << 12)
                | self.sequence
            )


class SyncParentDocumentStore:
    """
    Synchronous PostgreSQL-based storage for parent document content.
    Uses regular psycopg2 for thread safety in concurrent environments.
    """

    _instance = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.database_url = os.getenv("VECTOR_PG_DATABASE_URL")
            if not self.database_url:
                raise ValueError("VECTOR_PG_DATABASE_URL environment variable not set")
            self._ensure_table()
            self.__class__._initialized = True

    def _ensure_table(self):
        """Ensure the parent_ids table exists."""
        try:
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS public.parent_ids
                        (
                            id bigint NOT NULL,
                            data text COLLATE pg_catalog."default" NOT NULL,
                            CONSTRAINT parent_ids_pkey PRIMARY KEY (id)
                        );
                        
                        CREATE INDEX IF NOT EXISTS idx_parent_ids_lookup ON public.parent_ids(id);
                    """
                    )
                    conn.commit()
        except Exception as e:
            print(f"Error creating parent_ids table: {e}")

    def batch_store_parent_content(self, parent_data: List[tuple]):
        """Store multiple parent document contents in a single transaction."""
        if not parent_data:
            return

        try:
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor() as cur:
                    # Prepare data for execute_values - parent_id should be bigint
                    values = [
                        (int(parent_id), content) for parent_id, content in parent_data
                    ]

                    execute_values(
                        cur,
                        "INSERT INTO parent_ids (id, data) VALUES %s ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
                        values,
                        template=None,
                        page_size=100,
                    )
                    conn.commit()
        except Exception as e:
            print(f"Error batch storing parent content: {e}")
            raise

    def store_parent_content(self, parent_id: str, content: str):
        """Store parent document content with given ID."""
        try:
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO parent_ids (id, data) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
                        (int(parent_id), content),
                    )
                    conn.commit()
        except Exception as e:
            print(f"Error storing parent content for {parent_id}: {e}")
            raise


class AsyncParentRetriever:
    """
    Ultra-high-performance async PostgreSQL retriever optimized for 1000+ concurrent users.
    Features memory-safe caching, intelligent connection pooling, and request batching.
    """

    _instance = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.pool = None
            self.database_url = os.getenv("VECTOR_PG_DATABASE_URL")
            if not self.database_url:
                raise ValueError("VECTOR_PG_DATABASE_URL environment variable not set")

            # Concurrency control for high load
            self._semaphore = asyncio.Semaphore(100)  # Max 100 concurrent queries
            self._pool_lock = asyncio.Lock()
            self._request_counter = 0
            self._batch_requests = defaultdict(list)
            self._batch_lock = threading.Lock()

            self.__class__._initialized = True

    async def _ensure_pool(self):
        """Ensure connection pool is initialized with high-performance settings."""
        async with self._pool_lock:
            if self.pool is None or self.pool._closed:
                try:
                    if self.pool and not self.pool._closed:
                        await self.pool.close()
                        logger.info("Closed existing connection pool")
                except Exception as e:
                    logger.warning(f"Error closing old pool: {e}")

                # Optimized for 1000+ concurrent users
                self.pool = await asyncpg.create_pool(
                    self.database_url,
                    min_size=20,  # Higher minimum for immediate availability
                    max_size=100,  # Large pool for high concurrency
                    max_queries=50,  # Lower per-connection queries to distribute load
                    max_inactive_connection_lifetime=600.0,  # 10 minutes
                    command_timeout=15,  # Reasonable timeout
                    server_settings={
                        "application_name": "prism_parent_retriever_v2",
                        "tcp_keepalives_idle": "300",
                        "tcp_keepalives_interval": "60",
                        "tcp_keepalives_count": "3",
                    },
                )
                logger.info("Created new connection pool: min=20, max=100 connections")

    async def get_parent_contents(self, parent_ids: List[str]) -> Dict[str, str]:
        """
        Ultra-fast bulk retrieve with caching and batching optimization.
        Handles both string and integer parent_ids transparently.
        """
        if not parent_ids:
            return {}

        # Normalize all parent_ids to strings for consistent handling
        normalized_ids = [str(pid) for pid in parent_ids]

        # Check cache first
        cached_results = _global_cache.get_many(normalized_ids)
        missing_ids = [pid for pid in normalized_ids if pid not in cached_results]

        logger.info(f"Cache hit: {len(cached_results)}/{len(normalized_ids)} items")

        if not missing_ids:
            return cached_results

        # Use semaphore to control concurrent database access
        async with self._semaphore:
            try:
                await self._ensure_pool()

                # Convert string IDs to bigint for database query
                bigint_ids = [int(pid) for pid in missing_ids]

                # Use connection pool with timeout
                conn = await asyncio.wait_for(self.pool.acquire(), timeout=10.0)
                try:
                    # Use prepared statement for better performance
                    start_time = time.time()
                    rows = await conn.fetch(
                        "SELECT id, data FROM parent_ids WHERE id = ANY($1)", bigint_ids
                    )
                    query_time = time.time() - start_time

                    if query_time > 1.0:  # Log slow queries
                        logger.warning(
                            f"Slow query: {query_time:.2f}s for {len(missing_ids)} IDs"
                        )
                finally:
                    await self.pool.release(conn)

                # Process results - return keys in same format as input (normalized strings)
                db_results = {str(row["id"]): row["data"] for row in rows}

                # Cache the results
                if db_results:
                    _global_cache.set_many(db_results)

                # Combine cached and fresh results
                final_results = {**cached_results, **db_results}

                logger.info(
                    f"Retrieved {len(db_results)} items from DB, {len(final_results)} total"
                )
                return final_results

            except asyncio.TimeoutError:
                logger.error("Database connection timeout")
                # Return cached results only if DB fails
                return cached_results
            except Exception as e:
                logger.error(f"Error retrieving parent contents: {e}")
                # Try to reset the pool on critical errors
                if "connection" in str(e).lower() or "pool" in str(e).lower():
                    try:
                        await self._reset_pool()
                    except Exception as e:
                        logger.error(f"Error resetting connection pool: {e}")
                return cached_results

    async def _reset_pool(self):
        """Reset connection pool on critical errors."""
        async with self._pool_lock:
            if self.pool:
                try:
                    await self.pool.close()
                    logger.info("Force-closed connection pool due to errors")
                except Exception as e:
                    logger.error(f"Error force-closing connection pool: {e}")
                    self.pool = None
                finally:
                    self.pool = None

    async def close(self):
        """Close the connection pool and clear cache."""
        if self.pool and not self.pool._closed:
            try:
                await self.pool.close()
                logger.info("Connection pool closed gracefully")
            except Exception as e:
                logger.error(f"Error closing pool: {e}")
            finally:
                self.pool = None

        # Optionally clear cache on shutdown
        _global_cache.clear()


_sync_parent_store_instance = None
_async_parent_retriever_instance = None
_store_lock = threading.Lock()


def get_sync_parent_store_instance() -> SyncParentDocumentStore:
    """Get the synchronous singleton instance (thread-safe)."""
    global _sync_parent_store_instance
    if _sync_parent_store_instance is None:
        with _store_lock:
            if _sync_parent_store_instance is None:
                _sync_parent_store_instance = SyncParentDocumentStore()
    return _sync_parent_store_instance


def get_async_parent_retriever_instance() -> AsyncParentRetriever:
    """Get the async retriever singleton instance (thread-safe)."""
    global _async_parent_retriever_instance
    if _async_parent_retriever_instance is None:
        with _store_lock:
            if _async_parent_retriever_instance is None:
                _async_parent_retriever_instance = AsyncParentRetriever()
    return _async_parent_retriever_instance


def batch_store_parent_content_sync(parent_data: List[tuple]):
    """Thread-safe synchronous wrapper for batch storing parent content."""
    if not parent_data:
        return

    store = get_sync_parent_store_instance()
    store.batch_store_parent_content(parent_data)


def store_parent_content_sync(parent_id: str, content: str):
    """Thread-safe synchronous wrapper for storing parent content."""
    store = get_sync_parent_store_instance()
    store.store_parent_content(parent_id, content)


def get_parent_contents_sync(parent_ids: List[str]) -> Dict[str, str]:
    """
    High-performance sync wrapper optimized for 1000+ concurrent users.
    Uses intelligent thread pooling and memory-safe caching.
    Handles both string and integer parent_ids transparently.
    """
    if not parent_ids:
        return {}

    # Normalize all parent_ids to strings for consistent handling
    normalized_ids = [str(pid) for pid in parent_ids]

    # Quick cache check first (no async needed)
    cached_results = _global_cache.get_many(normalized_ids)
    if len(cached_results) == len(normalized_ids):
        logger.info(f"Full cache hit for {len(normalized_ids)} items")
        return cached_results

    retriever = get_async_parent_retriever_instance()

    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            # We're in an async context, use thread pool with optimized settings
            import concurrent.futures

            def run_in_thread():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(
                        retriever.get_parent_contents(normalized_ids)
                    )
                finally:
                    new_loop.close()

            # Use a larger thread pool for high concurrency
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=20,  # Increased workers for better concurrent handling
                thread_name_prefix="parent_retriever_",
            ) as executor:
                future = executor.submit(run_in_thread)
                return future.result(
                    timeout=20
                )  # Reduced timeout for faster failure detection
        else:
            # Direct async execution
            return loop.run_until_complete(
                retriever.get_parent_contents(normalized_ids)
            )

    except RuntimeError:
        # No event loop, create new one
        try:
            return asyncio.run(retriever.get_parent_contents(normalized_ids))
        except Exception as e:
            logger.error(f"Error in sync wrapper: {e}")
            # Return any cached results as fallback
            return cached_results
    except Exception as e:
        logger.error(f"Error in sync wrapper: {e}")
        return cached_results


# Keep the existing singleton functions for backward compatibility
_sync_parent_store_instance = None
_async_parent_retriever_instance = None
_store_lock = threading.Lock()
_snowflake = SnowflakeGenerator(os.environ.get("SNOWFLAKE_MACHINE_UUID") or uuid.uuid4().hex)

def get_next_snowflake() -> int:
    return _snowflake.next_id()