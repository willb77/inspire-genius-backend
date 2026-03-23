"""
Utility functions for image conversion and processing.
"""

import base64
from io import BytesIO
from typing import List

from pdf2image import convert_from_path
from pypdf import PdfReader


def get_pdf_page_count(pdf_path: str) -> int:
    """
    Get the total number of pages in a PDF file.
    
    Args:
        pdf_path (str): Path to the PDF file
    
    Returns:
        int: Total number of pages in the PDF
        
    Raises:
        Exception: If the PDF cannot be read
    """
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PdfReader(file)
            return len(pdf_reader.pages)
    except Exception as e:
        print(f"Error reading PDF page count: {e}")
        return 0


def pages_to_base64_images(pdf_path: str, start_page: int, end_page: int) -> List[str]:
    """
    Converts a range of PDF pages to base64 encoded PNG images.
    
    Automatically limits the page range to the actual number of pages in the PDF.
    If the end_page exceeds the total pages, it will use the total page count instead.
    
    Args:
        pdf_path (str): Path to the PDF file
        start_page (int): Starting page number (1-indexed)
        end_page (int): Ending page number (1-indexed, inclusive). Will be capped at total pages.
    
    Returns:
        List[str]: List of base64 encoded PNG images
        
    Raises:
        ValueError: If the page range is invalid or file cannot be processed
    """
    try:
        if start_page < 1 or end_page < start_page:
            raise ValueError(f"Invalid page range: start_page={start_page}, end_page={end_page}")
        
        # Get total pages in PDF and adjust end_page if needed
        total_pages = get_pdf_page_count(pdf_path)
        if total_pages == 0:
            raise ValueError(f"Could not read PDF or PDF is empty: {pdf_path}")
        
        # Cap end_page to total_pages
        adjusted_end_page = min(end_page, total_pages)
        
        print(f"Converting PDF pages {start_page} to {adjusted_end_page} (Total pages: {total_pages})")
        
        images_b64 = []
        
        for page_num in range(start_page, adjusted_end_page + 1):
            try:
                imgs = convert_from_path(pdf_path, dpi=300, first_page=page_num, last_page=page_num)
                if imgs:
                    buf = BytesIO()
                    imgs[0].save(buf, format="PNG")
                    images_b64.append(base64.b64encode(buf.getvalue()).decode("utf-8"))
            except Exception as e:
                error_msg = str(e)
                # Check if this is a poppler-related error
                if "poppler" in error_msg.lower() or "Unable to get page count" in error_msg:
                    print(f"Error: Poppler is not installed or not in PATH. Please install poppler-utils.")
                    print(f"  - On macOS: brew install poppler")
                    print(f"  - On Ubuntu/Debian: sudo apt-get install poppler-utils")
                    print(f"  - On Windows: Download from https://github.com/oschwartz10612/poppler-windows/releases/")
                    raise ValueError(
                        "Poppler is required for PDF image conversion but is not installed. "
                        "Please install poppler-utils on your system."
                    )
                print(f"Error converting page {page_num}: {e}")
                continue

        if not images_b64:
            raise ValueError(
                f"Failed to convert any pages from PDF. This may be due to missing dependencies like poppler."
            )

        return images_b64
    except Exception as e:
        print(f"Error converting PDF pages: {e}")
        raise e

