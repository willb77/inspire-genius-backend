import asyncio
import concurrent.futures
import math
from typing import Dict, List, Tuple

from langchain_core.documents import Document
from langchain_milvus import Milvus

from ai.file_services.vector_utils.parent_store import (
    get_async_parent_retriever_instance,
    get_parent_contents_sync,
)
from prism_inspire.core.log_config import logger

# Legacy FAISS functions - deprecated with Milvus migration
# These functions are kept for backward compatibility but should not be used in new code


def compute_search_strategy(file_count: int) -> int:
    """
    Compute search strategy based on total file count.
    
    Rules:
    - 4 or fewer files: search each file individually (number of searches = file count)
    - More than 4 files: divide into 2 groups (number of searches = 2)
    
    Examples:
    - 3 files: 3 searches (each file individually)
    - 4 files: 4 searches (each file individually)  
    - 5 files: 2 searches (divide into 2 groups)
    - 8 files: 2 searches (divide into 2 groups)
    - 20 files: 2 searches (divide into 2 groups)
    
    Args:
        file_count: Number of files
        
    Returns:
        Number of searches to perform
    """
    if file_count <= 4:
        return file_count  # Search each file individually
    else:
        return 2  # Always divide into 2 groups for more than 4 files





def _create_search_groups(file_ids: List[str]) -> List[List[str]]:
    """
    Create search groups based on file count strategy.
    
    Args:
        file_ids: List of file IDs
        
    Returns:
        List of groups, where each group is a list of file IDs
    """
    file_count = len(file_ids)
    
    if file_count <= 4:
        # Each file gets its own group (individual searches)
        return [[file_id] for file_id in file_ids]
    else:
        # Divide into 2 groups
        mid_point = math.ceil(file_count / 2)
        group1 = file_ids[:mid_point]
        group2 = file_ids[mid_point:]
        return [group1, group2]


async def _perform_optimized_search_async(
    vector_store: Milvus, query: str, k: int, filter: str, file_ids: List[str] = None
) -> List[Document]:
    """
    Optimized search that uses provided file_ids to create appropriate search groups.
    """
    if not file_ids:
        # Standard single search when no file IDs provided
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: vector_store.similarity_search(query=query, k=k, expr=filter)
        )
    
    # Create search groups based on strategy
    search_groups = _create_search_groups(file_ids)
    num_searches = len(search_groups)
    
    logger.info(f"Files: {len(file_ids)}, Groups: {len(search_groups)}, Searches: {num_searches}")
    
    async def search_file_group(group: List[str]) -> List[Document]:
        """Search a group of files together."""
        if len(group) == 1:
            # Single file search
            if filter:
                group_filter = f'{filter} and file_id == "{group[0]}"'
            else:
                group_filter = f'file_id == "{group[0]}"'
        else:
            # Multiple files search
            file_ids_str = ", ".join(f'"{fid}"' for fid in group)
            if filter:
                group_filter = f'{filter} and file_id in [{file_ids_str}]'
            else:
                group_filter = f'file_id in [{file_ids_str}]'
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: vector_store.similarity_search(
                query=query, k=k, expr=group_filter
            )
        )
    
    # Run searches for all groups concurrently
    group_tasks = [search_file_group(group) for group in search_groups]
    group_results = await asyncio.gather(*group_tasks, return_exceptions=True)
    
    # Combine results from all groups
    all_matches = []
    for i, result in enumerate(group_results):
        if isinstance(result, Exception):
            logger.error(f"Search failed for group {i}: {result}")
        else:
            all_matches.extend(result)
    
    return all_matches


def _perform_vector_searches(
    vector_store: Milvus, query: List[str] | str, k: int, filter: str, max_workers: int
) -> List[Document]:
    """Performs similarity searches, handling single or multiple queries in parallel."""
    queries = query if isinstance(query, list) else [query]
    if not queries:
        return []

    def search_single_query(q: str) -> List[Document]:
        return vector_store.similarity_search(query=q, k=k, expr=filter)

    all_matches = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(max_workers, len(queries))
    ) as executor:
        future_to_query = {executor.submit(search_single_query, q): q for q in queries}
        for future in concurrent.futures.as_completed(future_to_query):
            try:
                matches = future.result(timeout=30)
                all_matches.extend(matches)
            except Exception as e:
                query_text = future_to_query[future]
                print(f"Search failed for query '{query_text}': {e}")
    return all_matches


async def _perform_vector_searches_async(
    vector_store: Milvus, query: List[str] | str, k: int, filter: str, file_ids: List[str] = None
) -> List[Document]:
    """Performs async similarity searches, handling single or multiple queries in parallel."""
    queries = query if isinstance(query, list) else [query]
    if not queries:
        return []

    # If single query, use optimized search
    if len(queries) == 1:
        return await _perform_optimized_search_async(vector_store, queries[0], k, filter, file_ids)

    # Multiple queries - run them in parallel
    async def search_single_query_async(q: str) -> List[Document]:
        return await _perform_optimized_search_async(vector_store, q, k, filter, file_ids)

    tasks = [search_single_query_async(q) for q in queries]
    all_matches = []
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"Search failed for query '{queries[i]}': {result}")
            else:
                all_matches.extend(result)
    except Exception as e:
        print(f"Async search batch failed: {e}")

    return all_matches


def _extract_parent_info(all_matches: List[Document]) -> Tuple[List[str], Dict]:
    """Extracts unique parent IDs and their metadata from search results."""
    parent_ids = []
    parent_metadata = {}
    seen_parent_ids = set()

    for i, doc in enumerate(all_matches):
        parent_id = doc.metadata.get("parent_id")

        if parent_id and parent_id not in seen_parent_ids:
            seen_parent_ids.add(parent_id)
            parent_ids.append(parent_id)
            parent_metadata[parent_id] = doc.metadata

    return parent_ids, parent_metadata


def _format_response(
    data_items: Optional[List[Tuple[str, Dict]]] = None,
    source: bool = False,
    report_str: Optional[Dict[str, str]] = None
) -> str:
    """Fast formatting of matched content and/or MAP report sections."""

    if not data_items and not report_str:
        return report_str

    matches_by_file = {}

    # Group matches by file_id (single pass)
    if data_items:
        for content, metadata in data_items:
            file_id = metadata.get("file_id")
            if not file_id:
                continue
            file_id = str(file_id)
            matches_by_file.setdefault(file_id, []).append((content, metadata))

    # Combine file IDs without extra loops
    all_file_ids = set(matches_by_file)
    if report_str:
        all_file_ids.update(map(str, report_str))

    file_sections = []
    append_section = file_sections.append  # local ref = faster

    for file_id in all_file_ids:
        parts = []
        append_part = parts.append  # local ref = faster

        # MAP / report section first
        if report_str and file_id in report_str:
            append_part("# Section: MAP")
            append_part(f"Content: {report_str[file_id]}")

        # Vector matches
        for item in matches_by_file.get(file_id, ()):
            content, metadata = item

            if source:
                append_part(f"# Source: {metadata.get('source', 'unknown')}")
                section = metadata.get("report_section")
                if section and section.lower() != "general":
                    append_part(f"# Section: {section}")

            append_part(f"Content: {content}")

        if parts:
            append_section("\n".join(parts))

    return "\n\n".join(file_sections)



def _process_matches(all_matches: List[Document], source: bool) -> str:
    """Processes search results, retrieves parent documents, and formats the response."""
    if not all_matches:
        return ""

    parent_ids, parent_metadata = _extract_parent_info(all_matches)

    if not parent_ids:
        data_items = [(doc.page_content, doc.metadata) for doc in all_matches]
    else:
        parent_contents = get_parent_contents_sync(parent_ids)
        data_items = [
            (content, parent_metadata.get(pid, {}))
            for pid in parent_ids
            if (content := parent_contents.get(str(pid)))  # Now handles type conversion
        ]

    return _format_response(data_items, source)


async def _process_matches_async(all_matches: List[Document], source: bool, report_str={}) -> str | list[dict]:
    """Asynchronously processes search results, retrieves parent documents, and formats the response."""
    if not all_matches:
        logger.info("DEBUG: No matches to process")
        return ""

    parent_ids, parent_metadata = _extract_parent_info(all_matches)

    if not parent_ids:
        data_items = [(doc.page_content, doc.metadata) for doc in all_matches]
    else:
        retriever = get_async_parent_retriever_instance()
        parent_contents = await retriever.get_parent_contents(parent_ids)

        data_items = []
        for pid in parent_ids:
            content = parent_contents.get(
                str(pid)
            )  # AsyncParentRetriever now handles type conversion
            if content:
                data_items.append((content, parent_metadata.get(pid, {})))

    return _format_response(data_items, source, report_str = report_str)


def get_similarity_search(
    vector_store: Milvus,
    query: List[str] | str,
    k: int = 4,
    source: bool = True,
    filter: str = None,
    max_workers: int = 4,
    file_ids: List[str] = None,
) -> str:
    """
    Perform a parallel similarity search on the Milvus vector store and retrieve parent documents.

    This function:
    1. Finds child documents matching the query (in parallel if multiple queries)
    2. Extracts parent_ids from matched children
    3. Retrieves parent content from PostgreSQL (already optimized for concurrency)
    4. Uses parent_ids for deduplication to avoid duplicate content

    Args:
        vector_store: The Milvus vector store instance
        query: The query string or list of query strings to search for
        k: The number of results to return
        source: Whether to include the source document in the results
        filter: Optional filter expression for Milvus queries
        max_workers: Maximum number of threads for parallel vector searches (default: 4)

    Returns:
        String containing all search results with parent document content
    """
    if not vector_store:
        print("Vector store is not available.")
        return ""

    all_matches = _perform_vector_searches(vector_store, query, k, filter, max_workers)
    return _process_matches(all_matches, source)


async def get_similarity_search_async(
    vector_store: Milvus,
    query: List[str] | str,
    k: int = 4,
    source: bool = True,
    filter: str = None,
    file_ids: List[str] = None,
    report_str = {}
) -> str | list[dict]:
    """
    Async version of get_similarity_search with optimal performance for concurrent operations.
    
    Automatically optimizes search strategy based on provided file_ids:
    - For 4 or fewer files: search each file individually 
    - For more than 4 files: divide into 2 groups
    
    Examples:
    - 3 files: 3 searches (each file individually)
    - 4 files: 4 searches (each file individually)
    - 5 files: 2 searches (divide into 2 groups: 3+2)
    - 8 files: 2 searches (divide into 2 groups: 4+4)
    - 20 files: 2 searches (divide into 2 groups: 10+10)

    This function:
    1. Uses provided file_ids list to determine search strategy
    2. Automatically determines optimal search grouping strategy
    3. Runs searches concurrently for maximum performance
    4. Retrieves parent content from PostgreSQL using native async operations
    5. Uses parent_ids for deduplication to avoid duplicate content

    Args:
        vector_store: The Milvus vector store instance
        query: The query string or list of query strings to search for
        k: The number of results to return per search
        source: Whether to include the source document in the results
        filter: Optional filter expression for Milvus queries (without file_id filters)
        file_ids: List of file IDs to search in (will be grouped automatically)

    Returns:
        String containing all search results with parent document content
    """
    if not vector_store:
        print("Vector store is not available.")
        return ""

    all_matches = await _perform_vector_searches_async(vector_store, query, k, filter, file_ids)
    data = await _process_matches_async(all_matches, source, report_str=report_str)
    return data
