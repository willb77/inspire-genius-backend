import asyncio
import os
from pprint import pprint

# Optional: load .env if you have python-dotenv installed; otherwise export env in the shell
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))
except Exception:
    pass

from ai.ai_agent_services.agent_services.agents.prism_coach_agent import get_coaches_db
# langchain Milvus store
async def main():
    store = get_coaches_db()
    # Try to show collection name if available
    coll_name = getattr(store, "collection_name", None) or getattr(store, "_collection_name", None)
    print("Coaches vector store object:", type(store))
    print("Collection name (if exposed):", coll_name)

    # Useful helper to inspect results
    def inspect_matches(matches):
        for i, item in enumerate(matches):
            # similarity_search_with_score returns (Document, score) in this project
            try:
                doc, score = item
            except Exception:
                doc = item
                score = None
            meta = getattr(doc, "metadata", {})
            content = getattr(doc, "page_content", "")[:400]
            print(f"\nMATCH #{i+1} score={score}")
            print("metadata keys:", list(meta.keys()))
            pprint(meta)
            print("content preview:", content)
    
    queries = ["career", "career development", "job benchmark", "Career Success Factor"]
    career_filter = 'category == "career_coach_knowledge"'

    # Search with the career filter
    for q in queries:
        print("\n\n=== Query with FILTER ===")
        print("query:", q)
        try:
            matches = store.similarity_search_with_score(q, k=10, expr=career_filter)
            print(f"Returned {len(matches)} matches for query '{q}' with filter")
            inspect_matches(matches)
        except Exception as e:
            print("Search with filter raised exception:", e)

    # Search without filter (to see what's stored)
    print("\n\n=== Query WITHOUT filter ===")
    try:
        matches = store.similarity_search_with_score("career", k=20)
        print("Returned", len(matches), "matches without filter")
        inspect_matches(matches[:10])
    except Exception as e:
        print("Search without filter raised exception:", e)

    # Collect categories seen in top results
    print("\n\n=== Collect categories in top results (no filter) ===")
    try:
        matches = store.similarity_search_with_score("career", k=100)
        categories = {}
        for doc, _ in matches:
            cat = doc.metadata.get("category")
            categories[cat] = categories.get(cat, 0) + 1
        print("Categories counts in top results:")
        pprint(categories)
    except Exception as e:
        print("Could not collect categories:", e)

if __name__ == "__main__":
    asyncio.run(main())