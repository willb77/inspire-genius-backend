#!/usr/bin/env python3
"""
Script to create a vector store from documents in Common Documents/ folder and alex_data.txt
"""

import os
from pathlib import Path
import uuid
from ai.file_services.vector_utils.document_utils import DocumentProcessor
from prism_inspire.core.milvus_client import milvus_client


def main():
    """
    Main function to create vector store from documents
    """
    # Define the base directory (current script location)
    base_dir = Path(__file__).parent
    
    # Define source folders and files
    common_docs_folder = base_dir / "Common Documents/PRISM-Professional/Removed"
    print(f"Looking for documents in: {common_docs_folder}")

    # Collect all document files
    document_files = []
    
    # Add all files from Common Documents folder
    if common_docs_folder.exists():
        for file_path in common_docs_folder.rglob("*"):
            if file_path.is_file():
                document_files.append(file_path)
                print(f"Added: {file_path}")
    else:
        print(f"Warning: {common_docs_folder} not found")
    
    if not document_files:
        print("No documents found to process!")
        return
    
    print(f"\nTotal documents to process: {len(document_files)}")
    
    # Initialize DocumentProcessor
    # processor = DocumentProcessor(
    #     user_id="3b7c0214-46c4-4c25-b6f1-a42a9b22ac96",
    #     category="prism_coach_knowledge",
    #     file_id=str(uuid.uuid4()),
    #     filename="coaches_knowledge_documents",
    # )

    processor = DocumentProcessor(
        user_id="3b7c0214-46c4-4c25-b6f1-a42a9b22ac96",
        category="prism_coach_professional_knowledge",
        file_id=str(uuid.uuid4()),
        filename="coaches_knowledge_documents",
    )

    # processor = DocumentProcessor(
    #     user_id="3b7c0214-46c4-4c25-b6f1-a42a9b22ac96",
    #     category="alex_knowledge",
    #     file_id=str(uuid.uuid4()),
    #     filename="coaches_knowledge_documents",
    # )
    
    try:
        # Load all documents
        print("\nLoading documents...")
        documents = processor.load_document(document_files)
        print(f"Loaded {len(documents)} documents")
        
        # Split documents into chunks
        print("Splitting documents into chunks...")
        chunks = processor.split_documents(documents)
        uuids = [str(uuid.uuid4()) for _ in range(len(chunks))]

        
        # Get Milvus vector store and add documents
        print("Adding documents to Milvus collection 'alex_knowledge'...")
        vector_store = milvus_client.get_store()
        vector_store.add_documents(chunks, ids=uuids)
        data = vector_store.similarity_search_with_score("who is alex")
        print(f"Search results: {data}")
        
        
        print("\nVector store updated successfully in Milvus!")
        print("Collection name: alex_knowledge")
        print(f"Total chunks processed and added: {len(chunks)}")
        
    except Exception as e:
        print(f"Error creating vector store: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
