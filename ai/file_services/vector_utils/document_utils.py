import concurrent.futures
import json
import shutil
import time
import pandas as pd
import toon
from collections import namedtuple
import base64
from io import BytesIO
from datetime import date, datetime
from pathlib import Path
from google.genai import types
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional, Tuple, Union

from langchain_core.documents import Document
from langchain_text_splitters.character import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    CSVLoader,
    Docx2txtLoader,
    PyPDFLoader,
    TextLoader,
    UnstructuredExcelLoader,

)
import asyncio
import chardet
from langchain_core.documents import Document
from ai.ai_agent_services.prompts import file_category_prompt

from ai.file_services.vector_utils.ai_tools import (
    PageRange,
    PrismPdfMapping,
    PrismDataSections,
    PrismReport,
    GETCategoryID,
    Splitter_prompt,
    narrative_prompt,
    data_sections_prompt
)
from ai.file_services.vector_utils.image_utils import pages_to_base64_images
from ai.file_services.vector_utils.parent_store import (
    SnowflakeGenerator,
    batch_store_parent_content_sync,
    store_parent_content_sync,
)
from prism_inspire.core.ai_client import openai_client, genai_client

FileWithID = namedtuple("FileWithID", ["file", "db_id", "name"])

# Use a single constant for the default 'No ID' sentinel to avoid duplication
NO_ID = "No ID"


def detect_encoding(file_path: Union[str, Path]) -> str:
    """
    Detect the encoding of a file using chardet.
    Returns 'utf-8' if detection fails or confidence is low.
    """
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read(10000)  # Read first 10KB
            if not raw_data:
                return 'utf-8'
            result = chardet.detect(raw_data)
            encoding = result['encoding']
            confidence = result['confidence']
            
            if encoding and confidence > 0.5:
                # Map common encodings if necessary
                if encoding.lower() == 'ascii':
                    return 'utf-8'
                return encoding
    except Exception as e:
        print(f"Error detecting encoding for {file_path}: {e}")
        
    return 'utf-8'


class GetDocumentCategoryID:
    """Class to handle category identification and PDF processing"""

    def __init__(self, file_path: str, categorys: str, client=openai_client, filename: str = "Unknown"):

        self.file_path = file_path
        self.categorys = categorys
        self.client = client
        self.filename = filename
        
    def _get_data_preview(self) -> str | None:
        """Get text preview for CSV/XLSX files"""
        try:
            file_lower = self.file_path.lower()
            if hasattr(self.file_path, 'lower'):
                path_str = str(self.file_path)
            else:
                 path_str = self.file_path

            if path_str.endswith('.csv'):
                encoding = detect_encoding(self.file_path)
                df = pd.read_csv(self.file_path, nrows=5, encoding=encoding)
                return df.to_string(index=False)
            elif path_str.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(self.file_path, nrows=5)
                return df.to_string(index=False)
            return None
        except Exception as e:
            print(f"Error reading file preview: {e}")
            return None

    def get_category_id(self) -> GETCategoryID | None:
        """Get document category ID for processing"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                user_content = []
                # Check if file is PDF or Data file
                path_str = str(self.file_path).lower()
                
                if path_str.endswith('.pdf'):
                    # Get first 5 pages of the PDF as base64 images
                    images = pages_to_base64_images(self.file_path, 1, 5)
                    image_messages = [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    }
                    for b64 in images
                    ]
                    
                    user_content = [
                        {"type": "text", "text": "Analyse this first 5 pages of the document and categorize the document accordingly. Actual filename is {filename}.".format(filename=self.filename)},
                    ] + image_messages
                
                elif path_str.endswith(('.csv', '.xlsx', '.xls')):
                    data_preview = self._get_data_preview()
                    if not data_preview:
                        print("Failed to get data preview")
                        return None
                        
                    user_content = [
                        {"type": "text", "text": f"Analyse this data preview (first 5 rows) and categorize the document accordingly. Actual filename is {self.filename}.\n\nData Preview:\n{data_preview}"},
                    ]
                
                else:
                    # Fallback or unknown type
                    print(f"Unsupported file type for categorization: {self.file_path}")
                    return None
                
                resp = self.client.beta.chat.completions.parse(
                        reasoning_effort="low",
                        model="gpt-5-nano",
                        messages=[
                            {"role": "system", "content": file_category_prompt.format(category_ids=self.categorys)},
                            {"role": "user", "content": user_content}
                        ],
                        response_format=GETCategoryID,
                    )
                parsed = resp.choices[0].message.parsed
                return parsed
            
            except Exception as e:
                print(f"Attempt {attempt + 1} failed to get category ID: {e}")
                if attempt == max_retries - 1:
                    print(f"Error getting category ID after {max_retries} attempts: {e}")
                    raise e
                time.sleep(2 * (attempt + 1))
        return None



class DocumentProcessor:
    """
    A service class for handling document loading and splitting.
    This class provides utilities for loading different types of documents
    and splitting them into smaller chunks for vector operations.
    """

    SUPPORTED_TEXT_EXTENSIONS = {".txt", ".md"}
    SUPPORTED_PDF_EXTENSIONS = {".pdf"}
    SUPPORTED_DOCX_EXTENSIONS = {".docx", ".doc"}
    SUPPORTED_CSV_EXTENSIONS = {".csv"}
    SUPPORTED_EXCEL_EXTENSIONS = {".xlsx", ".xls"}

    def __init__(self, *args, **kwargs):
        """Initialize the document processor."""
        # Pass only keyword args into the initializer (remove positional args)
        self._initialize(**kwargs)

    def _initialize(self, **kwargs):
        """Initialize the document processor with specified parameters.

        Args:
            **kwargs: Keyword arguments including:
                - chunk_size (int): The size of each document chunk (default: 1000)
                - chunk_overlap (int): The overlap between chunks (default: 200)
        """
        # Keep signature simple; positional args are unused
        self.chunk_size = kwargs.get("chunk_size", 2000)
        self.chunk_overlap = kwargs.get("chunk_overlap", 400)
        self.user_id = kwargs.get("user_id", "None")
        self.category = kwargs.get("category", "Default")
        self.file_id = kwargs.get("file_id", NO_ID)
        self.filename = kwargs.get("filename", "Unknown")

    @staticmethod
    def _get_file_extension(file_path: Union[str, Path]) -> str:
        """
        Get the file extension from the given file path.

        Args:
            file_path (Union[str, Path]): Path to the file

        Returns:
            str: The file extension (including the dot)
        """
        return Path(file_path).suffix.lower()

    def load_document(self, file_paths: List[Union[str, Path]]) -> List[Document]:
        """
        Load documents from the given file paths using the appropriate loaders.

        Args:
            file_paths (List[Union[str, Path]]): List of paths to the documents to load

        Returns:
            List[Document]: List of loaded documents from all files

        Raises:
            ValueError: If any file extension is not supported
            FileNotFoundError: If any file does not exist
        """
        all_documents = []

        for file_path in file_paths:
            file_path = Path(file_path)
            extension = self._get_file_extension(file_path)

            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")

            # Check if file has no extension or empty extension
            if not extension or extension == ".":
                supported_formats = (
                    self.SUPPORTED_TEXT_EXTENSIONS
                    | self.SUPPORTED_PDF_EXTENSIONS
                    | self.SUPPORTED_DOCX_EXTENSIONS
                    | self.SUPPORTED_CSV_EXTENSIONS
                    | self.SUPPORTED_EXCEL_EXTENSIONS
                )
                raise ValueError(
                    f"Unsupported file format: {extension}. "
                    f"Supported formats are: {', '.join(sorted(supported_formats))}"
                )

            if extension in self.SUPPORTED_TEXT_EXTENSIONS:
                loader = TextLoader(str(file_path))
            elif extension in self.SUPPORTED_PDF_EXTENSIONS:
                loader = PyPDFLoader(str(file_path))
            elif extension in self.SUPPORTED_DOCX_EXTENSIONS:
                loader = Docx2txtLoader(str(file_path))
            elif extension in self.SUPPORTED_CSV_EXTENSIONS:
                encoding = detect_encoding(file_path)
                loader = CSVLoader(str(file_path), encoding=encoding)
            elif extension in self.SUPPORTED_EXCEL_EXTENSIONS:
                loader = UnstructuredExcelLoader(str(file_path))
            else:
                supported_formats = (
                    self.SUPPORTED_TEXT_EXTENSIONS
                    | self.SUPPORTED_PDF_EXTENSIONS
                    | self.SUPPORTED_DOCX_EXTENSIONS
                    | self.SUPPORTED_CSV_EXTENSIONS
                    | self.SUPPORTED_EXCEL_EXTENSIONS
                )
                raise ValueError(
                    f"Unsupported file format: {extension}. "
                    f"Supported formats are: {', '.join(supported_formats)}"
                )

            documents = loader.load()
            all_documents.extend(documents)

        return all_documents

    def split_documents(self, documents: List[Document]) -> List[Document]:
        """
        Split a list of documents into parent-child chunks.

        Args:
            documents (List[Document]): List of documents to split

        Returns:
            List[Document]: List of child documents with parent ID references
        """
        gentr = SnowflakeGenerator(self.user_id)
        # Step 1: Split into parents (large chunks)
        parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=200,
            separators=["\n\n", "\n", " ", ""],
        )
        parent_docs = parent_splitter.split_documents(documents)

        # Step 2: Split each parent into smaller children
        child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=400,
            chunk_overlap=80,
            separators=["\n\n", "\n", " ", ""],
        )

        child_docs = []
        parent_data_batch = []

        for i, parent in enumerate(parent_docs):
            parent_id = gentr.next_id()

            parent_data_batch.append((parent_id, parent.page_content))

            children = child_splitter.split_text(parent.page_content)
            for child in children:
                child_doc = Document(
                    page_content=child,
                    metadata={
                        "parent_id": parent_id,
                        "report_section": "general",  # Default value for non-PRISM reports
                        "user_id": self.user_id,
                        "category": self.category,
                        "file_id": self.file_id,
                        "source": self.filename,
                    },
                )
                child_docs.append(child_doc)

        # Batch store all parent content at once to avoid concurrent operations
        if parent_data_batch:
            self._batch_store_parent_content(parent_data_batch)

        return child_docs

    def _batch_store_parent_content(self, parent_data_batch: List[tuple]):
        """Store parent content in batch to avoid concurrent database operations."""
        try:
            batch_store_parent_content_sync(parent_data_batch)
        except Exception as e:
            print(f"Error batch storing parent content: {e}")
            # Fallback to individual storage if batch fails
            for parent_id, content in parent_data_batch:
                try:
                    store_parent_content_sync(parent_id, content)
                except Exception as individual_error:
                    print(
                        f"Error storing parent content for {parent_id}: {individual_error}"
                    )
                    # Continue with other parent documents even if one fails


async def store_report_str_async(file_id: str, report_str: str) -> None:
    """
    Asynchronously store the stringified report to the database without blocking.
    This function is designed to run in the background after file upload completes.
    
    Args:
        file_id (str): The file ID to associate with the report
        report_str (str): The stringified PRISM report content
    """
    try:
        from prism_inspire.db.session import SessionLocal
        from sqlalchemy import text
        import uuid
        
        session = SessionLocal()
        try:
            # Use raw SQL to insert since there's no ORM model yet
            stmt = text(
                """
                INSERT INTO reports (id, file_id, report_str, created_at, updated_at, is_deleted)
                VALUES (:id, :file_id, :report_str, NOW(), NOW(), false)
                ON CONFLICT (file_id) DO UPDATE
                SET report_str = :report_str, updated_at = NOW()
                """
            )
            
            session.execute(
                stmt,
                {
                    "id": str(uuid.uuid4()),
                    "file_id": file_id,
                    "report_str": report_str,
                },
            )
            session.commit()
            print(f"Successfully stored report_str for file_id: {file_id}")
        except Exception as db_error:
            session.rollback()
            print(f"Error storing report_str for file_id {file_id}: {db_error}")
        finally:
            session.close()
    except Exception as e:
        print(f"Unexpected error in store_report_str_async: {e}")


def process_uploaded_files(
    uploaded_files: List[FileWithID],
    user_id: str = "guest",
    category: str = "General",
) -> List[Document]:
    """
    Process uploaded files using DocumentProcessor.

    Args:
        uploaded_files (List[FileWithID]): List of files uploaded from FastAPI
        user_id (str): ID of the user uploading
        category (str): Document category

    Returns:
        List[Document]: List of document chunks ready for vector storage
    """
    all_chunks = []
    report_data_to_store = []  # Track report_str data for async storage

    with TemporaryDirectory() as temp_dir:
        # Process each file individually with its own db_id
        for file in uploaded_files:
            uploaded_file = file.file
            db_id = file.db_id
            file_path = Path(temp_dir) / file.file.filename

            with open(file_path, "wb") as buffer:
                # Reset file pointer to beginning
                uploaded_file.file.seek(0)
                # Copy the file content
                shutil.copyfileobj(uploaded_file.file, buffer)

            # Check if this is a PRISM report
            if category.lower() == "reports":
                try:
                    # Process PRISM report and get documents and report_str
                    documents, report_str = process_prism_report(
                        file_path=str(file_path),
                        user_id=user_id,
                        category=category,
                        file_id=str(db_id),
                        filename=str(file.name),
                    )
                    all_chunks = documents
                    # Track report_str for async storage
                    if report_str:
                        report_data_to_store.append((str(db_id), report_str))
                    continue
                except ValueError as e:
                    raise ValueError(str(e))
            else:
                processor = DocumentProcessor(
                    user_id=user_id,
                    category=category,
                    file_id=str(db_id),
                    filename=str(file.name),
                )
                documents = processor.load_document([file_path])
                chunks = processor.split_documents(documents)
                all_chunks.extend(chunks)
    
    # Trigger async storage of report_str data without blocking
    if report_data_to_store:
        for file_id, report_str in report_data_to_store:
            # Create background task to store report_str
            try:
                asyncio.create_task(store_report_str_async(file_id, report_str))
            except RuntimeError:
                # If no event loop is running, try to run it in a new loop
                print(f"Warning: Could not create async task for file_id {file_id}, will try sync storage")
                try:
                    asyncio.run(store_report_str_async(file_id, report_str))
                except Exception as e:
                    print(f"Failed to store report_str for {file_id}: {e}")
    
    return all_chunks



def get_prism_label(val):
    """Converts numerical score to PRISM label string."""
    try:
        n = float(val)
        if pd.isna(n): return None
        if n >= 75: label = "Very High"
        elif 65 <= n <= 74: label = "Natural"
        elif 50 <= n <= 64: label = "Moderate"
        elif 36 <= n <= 49: label = "Low Moderate"
        else: label = "Very Low"
        return f"{int(n)} ({label})"
    except (ValueError, TypeError):
        return val


class ReportLoader:
    """
    A class to analyze different sections of a PDF document by identifying
    page ranges for specific topics, converting those pages to images,
    and using an AI model to generate insights.
    """

    def __init__(self, model: str = "gemini-3-flash-preview", *args, **kwargs):
        """
        Initializes the ReportLoader.

        Args:
            client: An OpenAI client instance.
            model: The model name to use for analysis.
        """
        self.client = genai_client
        self.model = model
        self.report_date = None
        self.page_range = None
        # _initialize no longer accepts positional args; forward only kwargs
        self._initialize(**kwargs)

    def _initialize(self, **kwargs):
        """Initialize the report loader with specified parameters.

        Args:
            **kwargs: Keyword arguments including:
                - user_id (str): User identifier
                - category (str): Document category
                - file_id (str): File identifier
                - filename (str): Source filename
        """
        # Keep signature simple; positional args are unused
        self.user_id = kwargs.get("user_id", "None")
        self.category = kwargs.get("category", "Report")
        self.file_id = kwargs.get("file_id", NO_ID)
        self.filename = kwargs.get("filename", "Unknown")
        self.report_str = None  # Store stringified report from Map section

    def _get_page_ranges(self, pdf_path: str) -> PrismPdfMapping:
        """
        Identifies and returns the page ranges for predefined sections of the PDF.
        """
        loader = PyPDFLoader(file_path=pdf_path, extract_images=True, mode="page")
        docs = loader.load()

        pages_content = ""
        for doc in docs:
            page_num = int(doc.metadata.get("page", 0) + 1)
            # Extracting initial and final text snippets for context
            header = doc.page_content[:150]
            footer_preview = doc.page_content[-300:][:-140]
            pages_content += f"page_no={page_num}:\n{header}\n  {footer_preview}\n--------------------------------\n"

        response = genai_client.models.generate_content(
            model=self.model,
            contents=f"Get page ranges for these pages: {pages_content}",
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                    thinking_level="LOW",
                ),
                system_instruction=Splitter_prompt,
                response_mime_type="application/json",
                response_schema=PrismPdfMapping,
            ),
        )
        self.page_range : PrismPdfMapping = response.parsed

        return self.page_range

    def _process_section(
        self, pdf_path: str, section_name: str, page_range: "PageRange", additional_info: str = ""
    ) -> Tuple[str, Any]:
        """Process a single section of the PDF and return its analysis result.

        Extracted from analyze_pdf to reduce cognitive complexity and nesting.
        """
        if page_range is None:
            print(f"Skipping section '{section_name}' as no page range was found.")
            return section_name, None

        print(
            f"Processing section: '{section_name}' (Pages: {page_range.start}-{page_range.end})"
        )

        try:
            imgs_b64 = pages_to_base64_images(pdf_path, page_range.start, page_range.end)
        except (ValueError, Exception) as e:
            print(f"Could not extract images for section '{section_name}': {e}")
            return section_name, None
        
        if not imgs_b64:
            print(f"Could not extract images for section '{section_name}'.")
            return section_name, None

        parts = []

        # Add the text instruction first
        parts.append(types.Part(text=f"Analyze the {section_name.replace('_', ' ')}"))

        # Add the images
        for b64 in imgs_b64:
            # Decode base64 string to bytes
            image_bytes = base64.b64decode(b64)
            # Create a Part object for the image
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/png"))


        max_retries = 3
        for attempt in range(max_retries):
            try:
                if section_name == "Map":
                    resp = genai_client.models.generate_content(
                        model=self.model,
                        contents=parts,
                        config=types.GenerateContentConfig(
                            thinking_config=types.ThinkingConfig(
                                thinking_level="MINIMAL",
                            ),
                            response_mime_type="application/json",
                            response_schema=PrismReport,  # Pass the Pydantic class directly
                        ),
                    )
                    
                    parsed_report: PrismReport = resp.parsed
                    
                    # Store report string without axis info
                    final_report_str = parsed_report.pstringify() + "\n\n" + additional_info
                    
                    return section_name, (parsed_report, final_report_str)
                else:
                    resp = genai_client.models.generate_content(
                        model=self.model,
                        contents=parts,
                        config=types.GenerateContentConfig(
                            thinking_config=types.ThinkingConfig(
                                thinking_level="MINIMAL",
                            ),
                            system_instruction=narrative_prompt,
                            temperature=0.65,
                        ),
                    )
                    return section_name, resp.text
            except Exception as e:
                print(f"Attempt {attempt + 1} failed for section '{section_name}': {e}")
                if attempt == max_retries - 1:
                    print(f"Failed to analyze section '{section_name}' after {max_retries} attempts: {e}")
                    raise e
                time.sleep(2 * (attempt + 1))

    def _process_map_section(
        self, data_content: str, additional_info: str = ""
    ) -> Tuple[str, Any]:
        """Process only the Map section from data content."""
        section_name = "Map"
        print(f"Processing data section: '{section_name}'")
        
        parts = []
        parts.append(types.Part(text=f"Analyze the {section_name} based on the following data:\n\n{data_content}"))
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = genai_client.models.generate_content(
                    model=self.model,
                    contents=parts,
                    config=types.GenerateContentConfig(
                        thinking_config=types.ThinkingConfig(
                            thinking_level="MINIMAL",
                        ),
                        response_mime_type="application/json",
                        response_schema=PrismReport,
                    ),
                )
                parsed_report: PrismReport = resp.parsed
                
                # Store report string without axis info
                final_report_str = parsed_report.pstringify() + "\n\n" + additional_info
                return section_name, (parsed_report, final_report_str)

            except Exception as e:
                print(f"Attempt {attempt + 1} failed for Map section: {e}")
                if attempt == max_retries - 1:
                    print(f"Failed to analyze Map section after {max_retries} attempts: {e}")
                    return section_name, None
                time.sleep(2 * (attempt + 1))

    def _process_text_sections(
        self, data_content: str
    ) -> Dict[str, str]:
        """Process all text-based sections in a single call."""
        print("Processing all text sections...")
        
        parts = []
        parts.append(types.Part(text=f"Data:\n\n{data_content}"))
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = genai_client.models.generate_content(
                    model=self.model,
                    contents=parts,
                    config=types.GenerateContentConfig(
                        thinking_config=types.ThinkingConfig(
                            thinking_level="MINIMAL",
                        ),
                        system_instruction=data_sections_prompt,
                        response_mime_type="application/json",
                        response_schema=PrismDataSections,
                    ),
                )
                parsed_sections: PrismDataSections = resp.parsed
                
                # Convert to dict and filter empty results
                results = {}
                model_dict = parsed_sections.model_dump()
                
                # Map model fields to user-friendly section names
                field_mapping = {
                    "work_apptitude_profile": "Work Aptitude Profile",
                    "core_traits_profile": "Core Traits Profile",
                    "work_preference_profile": "Work Preference Profile",
                    "career_development_analysis": "Career Development Analysis",
                    "emotional_intelligence_report": "Emotional Intelligence Report",
                    "big_five_report": "The Big Five Report",
                    "mental_toughness_report": "Mental Toughness Report",
                }
                
                for field, value in model_dict.items():
                    if value and value.strip() and value != "Data not available":
                        section_name = field_mapping.get(field, field)
                        results[section_name] = section_name + ":\n\n" + value
                return results

            except Exception as e:
                print(f"Attempt {attempt + 1} failed for text sections: {e}")
                if attempt == max_retries - 1:
                    print(f"Failed to analyze text sections after {max_retries} attempts: {e}")
                    return {}
                time.sleep(2 * (attempt + 1))
        return {}



    def _parse_prism_dataframe(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Parses the PRISM dataframe extracting sections using header keywords.
        """
        pd.set_option('future.no_silent_downcasting', True)
        
        final_report = {}
        
        # 1. METADATA DISCOVERY & FORMAT DETECTION
        # We need to find the "anchor" - where does the map data (Underlying/Adapted) live?
        map_col_idx = -1
        underlying_row_idx = -1
        
        # Scan first 2 columns and first 10 rows for "Underlying"
        for c in [0, 1]:
            if c >= len(df.columns): continue
            for r in range(min(10, len(df))):
                val = str(df.iloc[r, c])
                if "Underlying" in val:
                    map_col_idx = c
                    underlying_row_idx = r
                    break
            if map_col_idx != -1: break
            
        # 2. NAME EXTRACTION
        candidate_name = "Candidate"
        
        if map_col_idx == -1:
            # Format C: Single Row Format (Chad)
            underlying_row_idx = 0 
            # Try grabbing name from cell (0,0) if it looks like a name
            possible_name = str(df.iloc[0, 0])
            if "Candidate" not in possible_name:
                candidate_name = possible_name
            elif len(df) > 1:
                 candidate_name = str(df.iloc[1, 0])
        elif map_col_idx == 0:
            # Format B: New Format (Alexander/Lee) - Map in Col 0
            # Name is usually in the header or the row above data
            if underlying_row_idx > 0:
                candidate_name = str(df.iloc[underlying_row_idx - 1, 0])
            else:
                candidate_name = str(df.columns[0])
        else:
            # Format A: Old Format (Gary) - Map in Col 1, Name in Col 0
            candidate_name = str(df.iloc[underlying_row_idx, 0])

        candidate_name = candidate_name.replace('\xa0', ' ').strip() # Clean invisible spaces

        # 3. GLOBAL METRIC NAMES (Row 0)
        # We grab the entire first row to use as column headers for data slices
        # This fixes the "Unnamed: 93" issue in Big Five
        row_0_metrics = df.iloc[0].tolist()
        
        # 4. SECTION EXTRACTION
        target_sections = [
            "Behavior Preferences", "Work Aptitudes", "Core Traits", 
            "Mental Toughness", "Emotional Intelligence", "Work Preference Profile", 
            "PRISM Career Development Analysis", "The Big Five Report"
        ]

        for section in target_sections:
            # -- Find Column Bounds using Headers --
            start_idx = None
            for i, col in enumerate(df.columns):
                if section.lower() in str(col).lower():
                    start_idx = i; break
            
            if start_idx is None: continue 
            
            # Find end of section
            end_idx = start_idx + 1
            for i in range(start_idx + 1, len(df.columns)):
                col_val = str(df.columns[i])
                if "Unnamed" not in col_val and "nan" != col_val.lower():
                    break
                end_idx = i + 1
            
            # -- Extract & Label Columns --
            section_slice = df.iloc[:, start_idx:end_idx].copy()
            
            # FIX: Rename columns using Row 0 metrics for this specific slice
            # This ensures 'Unnamed: 93' becomes 'agreeableness'
            current_metrics = row_0_metrics[start_idx:end_idx]
            clean_cols = []
            for m in current_metrics:
                if pd.isna(m) or str(m).lower() == 'nan':
                    # Fallback if Row 0 is empty
                    clean_cols.append(str(df.columns[start_idx + len(clean_cols)]))
                else:
                    clean_cols.append(str(m).strip())
            
            section_slice.columns = clean_cols
            
            # -- Apply Value Formatting --
            # Use .map() for Pandas 2.1+, use .applymap() if on older version
            try:
                section_slice = section_slice.map(get_prism_label)
            except AttributeError:
                section_slice = section_slice.applymap(get_prism_label)
            
            # -- Logic Split --
            is_behavior = "Behavior" in section
            
            if is_behavior and map_col_idx != -1:
                # === BEHAVIOR: Scan for ALL Maps ===
                behavior_dict = {}
                valid_keywords = ["Underlying", "Adapted", "Consistent"]
                
                for idx in range(len(df)):
                    # Check the map column for this specific row
                    row_map_val = str(df.iloc[idx, map_col_idx])
                    
                    if any(k in row_map_val for k in valid_keywords):
                        clean_map = row_map_val.replace(" Map", "").strip()
                        # Use REAL NAME for Behavior
                        key_name = f"{candidate_name} ({clean_map})"
                        
                        # Get data for this row
                        row_data = section_slice.iloc[idx].dropna().to_dict()
                        if row_data:
                            behavior_dict[key_name] = row_data
                
                final_report[section] = behavior_dict
                
            else:
                # === OTHERS: Flattened (No Name) ===
                target_row = underlying_row_idx
                if target_row == -1: target_row = 0
                
                # Check if target row exists in slice
                if target_row < len(section_slice):
                    row_data = section_slice.iloc[target_row].dropna().to_dict()
                    
                    # Clean up keys: remove the section title itself if it appears as a key
                    clean_row_data = {}
                    for k, v in row_data.items():
                        if section.lower() not in k.lower() and "unnamed" not in k.lower():
                            clean_row_data[k] = v
                    
                    if clean_row_data:
                        final_report[section] = clean_row_data
        return final_report

    def analyze_data_file(self, file_path: str) -> Dict[str, Any]:
        """
        Analyzes a CSV/Excel data file for Map, OtherSections, and all standard PRISM sections.
        """
        print(f"Reading data file: {file_path}")
        try:
            path_str = str(file_path).lower()
            if path_str.endswith('.csv'):
                encoding = detect_encoding(file_path)
                df = pd.read_csv(file_path, encoding=encoding)
            elif path_str.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file_path)
            else:
                raise ValueError("Unsupported data file format")
            
            # Parse the dataframe using deterministic logic
            parsed_sections = self._parse_prism_dataframe(df)
            
        except Exception as e:
            raise ValueError(f"Failed to read or parse data file: {e}")

        results = {}
        additional_info = " "
        
        # 1. Process Map section (Behavior Preferences)
        if "Behavior Preferences" in parsed_sections:
            behavior_data = parsed_sections.pop("Behavior Preferences")
            # Convert to TOON format for Map analysis
            toon_data = toon.encode(behavior_data)
            try:
                name, result = self._process_map_section(toon_data, additional_info)
                if result is not None:
                    if isinstance(result, tuple) and hasattr(result[0], '_build_axis'):
                        prism_report, _ = result
                        axis_points = prism_report._build_axis()
                        opposite_behaviours = prism_report.build_opposite_behaviours()
                        quadrant_summaries = prism_report._build_quadrant_summaries()
                        behaviour_summary = prism_report.build_behaviour_summary()

                        additional_calcs = "### Quick Reference from Map \n" + "\n".join(behaviour_summary)
                        additional_calcs += "\n\n" + "### Quadrant Summaries \n" + quadrant_summaries
                        additional_calcs += "\n\n" + "### Axis Points \n" + axis_points
                        additional_calcs += "\n\n" + "### Opposite Behaviours \n" + opposite_behaviours
                        
                        results["Map Additional Calculations for AI"] = additional_calcs
                    results[name] = result
            except Exception as e:
                print(f"Error processing Map section: {e}")
                raise e
        
        # 2. Process Other Sections (Direct Extraction)
        try:
            for section, data in parsed_sections.items():
                if data:
                     # Add formatted section to results
                     formatted_data = toon.encode(data)
                     results[section] = f"{section}:\n\n{formatted_data}"

            # Check if optional sections are missing
            optional_sections = [
                "Emotional Intelligence", # Keys in new parser are slightly different
                "The Big Five Report",
                "Mental Toughness" 
            ]
            
            missing_optional_count = sum(1 for section in optional_sections if section not in results and section + " Report" not in results)
            
            if missing_optional_count == len(optional_sections):
                warning_info = (
                    "\n\nThis is not PRISM Professional Report. "
                    "Only PRISM professional reports contain Emotional Intelligence (EQ), Big Five and Mental Toughness analysis. "
                    "When asked about these sections, tell that this is not PRISM Professional report. "
                    "Tell the user to upload professional report to know about these sections."
                )
                
                # Append this info to the Map section result if available
                if "Map" in results and isinstance(results["Map"], tuple):
                     prism_report, report_str = results["Map"]
                     results["Map"] = (prism_report, report_str + warning_info)
                
        except Exception as e:
             print(f"Error processing text sections: {e}")
             raise e

        print("Data analysis complete.")
        return results

    def analyze_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        Orchestrates the full analysis of the PDF using a thread pool for concurrent processing.

        Args:
            pdf_path: The file path to the PDF report.

        Returns:
            A dictionary containing the analysis results for each section.
        """
        print("Determining page ranges for sections...")
        section_mapping = self._get_page_ranges(pdf_path)

        if not section_mapping.is_prism_report:
            raise ValueError("The uploaded file is not valid PRISM report.")

        results = {}
        additional_info = ""
        print("Analyzing sections...")

        # Use the extracted helper to process sections; this reduces nesting and complexity
        process_fn = self._process_section

        # Build dictionary of section mappings (include optional ones when present)
        section_mappings = {
            "Map": section_mapping.Map,
            "prism_profile_narrative": section_mapping.prism_profile_narrative,
            "work_preference_profile": section_mapping.work_preference_profile,
            "career_development_analysis": section_mapping.career_development_analysis,
        }

        if section_mapping.emotional_intelligence_report:
            section_mappings["emotional_intelligence_report"] = (
                section_mapping.emotional_intelligence_report
            )
        if section_mapping.big_five_report:
            section_mappings["big_five_report"] = section_mapping.big_five_report
        if section_mapping.mental_toughness_report:
            section_mappings["mental_toughness_report"] = (
                section_mapping.mental_toughness_report
            )

        if not section_mapping.emotional_intelligence_report and not section_mapping.big_five_report and not section_mapping.mental_toughness_report:
            additional_info = (
            "This is not PRISM Professional Report."
            "Only PRISM professional reports contain Emotional Intelligence (EQ), Big Five and Mental Toughness analysis. when asked about these sections, tell that this is not PRISM Professional report. Tell the user to upload professional report to know about these sections."
            )
        # Use a thread pool to process sections concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = {
                executor.submit(
                    process_fn, pdf_path, section_name, page_range, additional_info
                ): section_name
                for section_name, page_range in section_mappings.items()
            }

            for future in concurrent.futures.as_completed(futures):
                section_name = futures[future]
                try:
                    section_name, result = future.result()
                    if result is not None:
                        # If Map section returns report instance, extract axis points
                        if section_name == "Map" and isinstance(result, tuple) and hasattr(result[0], '_build_axis'):
                            prism_report, _ = result
                            axis_points = prism_report._build_axis()
                            opposite_behaviours = prism_report.build_opposite_behaviours()
                            quadrant_summaries = prism_report._build_quadrant_summaries()
                            behaviour_summary = prism_report.build_behaviour_summary()

                            additional_calcs = "### Quick Reference from Map \n" + "\n".join(behaviour_summary)
                            additional_calcs += "\n\n" + "### Quadrant Summaries \n" + quadrant_summaries
                            additional_calcs += "\n\n" + "### Axis Points \n" + axis_points
                            additional_calcs += "\n\n" + "### Opposite Behaviours \n" + opposite_behaviours
                        
                            results["Map (Additional Calculations for AI)"] = additional_calcs

                    results[section_name] = result if isinstance(result, tuple) else section_name + "\n" + result
                except Exception as e:
                    print(f"Error processing section '{section_name}': {e}")
                    raise e

        print("Analysis complete.")
        return results

    def create_documents_from_analysis(
        self, analysis_results: Dict[str, Any]
    ) -> List[Document]:
        """
        Convert analysis results into Document objects with parent-child structure.
        Excludes the "Map" section from documents and splits them into parent-child chunks.

        Args:
            analysis_results: Dictionary containing section names and their content

        Returns:
            List[Document]: List of child Document objects for each section (excluding Map)
        """
        docs = []
        gentr = SnowflakeGenerator(self.user_id)
        for section, content in analysis_results.items():

            if section == "Map":
                # Extract report_str from tuple (prism_report_object, stringified_content)
                if isinstance(content, tuple):
                    _, report_str = content
                    self.report_str = report_str 
                    content = report_str
                else:
                    self.report_str = content
                continue
            # Create a Document object for each item
            doc = Document(
                page_content=section + ": " + content,
                metadata={
                    "report_section": section,
                    "user_id": self.user_id,
                    "category": self.category,
                    "file_id": self.file_id,
                    "source": self.filename,
                },
            )
            docs.append(doc)

        # Step 1: Split into parents (large chunks)
        parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1500,
            chunk_overlap=150,
            separators=["\n\n", " "],
        )
        parent_docs = parent_splitter.split_documents(docs)

        # Step 2: Split each parent into smaller children
        child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=350,
            chunk_overlap=30,
            separators=["\n\n", " "],
        )

        child_docs = []
        parent_data_batch = []

        for i, parent in enumerate(parent_docs):
            parent_id = gentr.next_id()

            parent_data_batch.append((parent_id, parent.page_content))

            children = child_splitter.split_text(parent.page_content)
            for child in children:
                child_doc = Document(
                    page_content=child,
                    metadata={"parent_id": parent_id, **parent.metadata},
                )
                child_docs.append(child_doc)

        if parent_data_batch:
            self._batch_store_parent_content(parent_data_batch)
        return child_docs

    def _batch_store_parent_content(self, parent_data_batch: List[tuple]):
        """Store parent content in batch to avoid concurrent database operations."""
        try:
            batch_store_parent_content_sync(parent_data_batch)
        except Exception as e:
            print(f"Error batch storing parent content: {e}")
            for parent_id, content in parent_data_batch:
                try:
                    store_parent_content_sync(parent_id, content)
                except Exception as individual_error:
                    print(
                        f"Error storing parent content for {parent_id}: {individual_error}"
                    )


def process_prism_report(
    file_path: str,
    user_id: str = "guest",
    category: str = "PRISM_Report",
    file_id: str = NO_ID,
    filename: str = "Unknown",
) -> Tuple[List[Document], Optional[str]]:
    """
    Process a PRISM report (PDF or CSV/Excel) using ReportLoader and return Document objects and Map data separately.

    Args:
        file_path (str): Path to the report file
        user_id (str): ID of the user uploading
        category (str): Document category
        file_id (str): File identifier
        filename (str): Source filename

    Returns:
        Tuple[List[Document], Optional[str]]: Documents for sections (excluding Map) and stringified report_str
    """
    report_loader = ReportLoader(
        client=genai_client,
        model="gemini-3-flash-preview",
        user_id=user_id,
        category=category,
        file_id=file_id,
        filename=filename,
    )

    try:
        # Analyze file based on extension
        path_str = str(file_path).lower()
        if path_str.endswith('.pdf'):
            analysis_results = report_loader.analyze_pdf(file_path)
        elif path_str.endswith(('.csv', '.xlsx', '.xls')):
            analysis_results = report_loader.analyze_data_file(file_path)
        else:
            raise ValueError(f"Unsupported report format: {Path(file_path).suffix}")

        # Create documents (excluding Map)
        documents = report_loader.create_documents_from_analysis(analysis_results)
        
        # Return documents and the extracted report_str for database storage
        return documents, report_loader.report_str
    except ValueError as e:
        raise ValueError(f"Report validation failed: {str(e)}")
    except Exception as e:
        print(f"Error processing PRISM report: {e}")
        raise ValueError(f"Error processing PRISM report: {str(e)}")
