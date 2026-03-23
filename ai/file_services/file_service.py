import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi_utils.cbv import cbv

from ai.agent_settings.schema import get_category_by_id, get_all_category
from ai.file_services.req_resp_parser import (
    BulkDeleteRequest,
    FileDownloadResponse,
    FileListResponse,
    MultipleFileUploadResponse,
)
from ai.file_services.schema import (
    create_file_record,
    get_file_by_id,
    get_file_category_by_file_id,
    get_files_by_user_id,
    get_files_by_user_id_paginated,
    soft_delete_file,
)
from ai.file_services.vector_utils.document_utils import (
    FileWithID,
    GetDocumentCategoryID,
    process_uploaded_files,
)
from ai.file_services.convertors import convert_table_to_pdf
from prism_inspire.core.file_utils import file_handler
from prism_inspire.core.log_config import logger
from prism_inspire.core.milvus_client import milvus_client
from users.auth import verify_token
from users.response import (
    SOMETHING_WENT_WRONG,
    SUCCESS_CODE,
    VALIDATION_ERROR_CODE,
    create_response,
)

went_wrong = "Something went wrong, please try again later"
INVALID_FILE_ID_FORMAT = "Invalid file ID format"
INVALID_CATEGORY_ID_FORMAT = "Invalid category ID format"
FILE_NOT_FOUND = "File not found"

file_service = APIRouter(prefix="/file_service", tags=["File Service"])


class FileUploadManager:
    """Comprehensive file upload management class"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.uploaded_files = []
        self.failed_files = []
        self.bundled = []
        self.category = None  # Will be set to N/A only if no category is detected
        self.category_uuid = None

    def validate_files_input(self, files: List[UploadFile]) -> bool:
        """Validate basic file input"""
        if not files or len(files) == 0:
            raise ValueError("No files provided")
        return True
    
    def get_category_str(self) -> str:
        """Get category string for logging or processing"""
        categories = get_all_category()
        category_str = ", ".join([f"{cat.id}: {cat.display_name}" for cat in categories])
        return category_str

    def process_category(self, category_id: Optional[str]) -> bool:
        """Process and validate category"""
        if category_id:
            try:
                self.category_uuid = UUID(category_id)
                self.category = get_category_by_id(self.category_uuid).name
            except ValueError:
                raise ValueError(INVALID_CATEGORY_ID_FORMAT)
        return True

    def validate_category_rules(self, files: List[UploadFile]) -> Optional[Dict]:
        """Validate category-specific rules"""
        if self.category and self.category.lower() == "reports" and len(files) > 1:
            return create_response(
                message="Only one file is allowed at once for the 'PRISM Reports' category.",
                status=False,
                error_code=VALIDATION_ERROR_CODE,
                status_code=400
            )
        return None

    def upload_single_file_to_storage(self, file: UploadFile) -> Optional[str]:
        """Upload file to storage and return S3 key"""
        return file_handler.save_file(file, self.user_id)

    def create_database_record(self, file: UploadFile, s3_key: str, filename: Optional[str] = None, converted_file_key: Optional[str] = None) -> Any:
        """Create file record in database"""
        file_extension = os.path.splitext(file.filename)[1].lower().lstrip(".")
        # Set category to N/A if still None at this point
        if self.category is None:
            self.category = "N/A"
        return create_file_record(
            user_id=UUID(self.user_id),
            filename=filename if filename else file.filename,
            file_type=file_extension,
            file_key=s3_key,
            category_id=self.category_uuid,
            converted_file_key=converted_file_key,
        )

    def add_to_success_list(self, file: UploadFile, file_record):
        """Add successful file to tracking lists"""
        # Generate presigned URL for the uploaded file
        temp_url = None
        converted_temp_url = None
        try:
            temp_url = file_handler.generate_presigned_url(file_record.file_key, expiration=1800)
        except Exception as url_error:
            logger.warning(f"Failed to generate presigned URL for file {file_record.id}: {url_error}")

        try:
            converted_key = getattr(file_record, "converted_file_key", None)
            if converted_key:
                converted_temp_url = file_handler.generate_presigned_url(converted_key, expiration=1800)
        except Exception as conv_error:
            logger.warning(f"Failed to generate presigned URL for converted file {getattr(file_record, 'id', None)}: {conv_error}")

        
        file_info = {
            "file_id": str(file_record.id),
            "filename": file_record.filename,
            "file_key": file_record.file_key,
            "file_type": file_record.file_type,
            "category_id": (
                str(file_record.category_id) if file_record.category_id else None
            ),
            "temp_url": temp_url,
            "converted_temp_url": converted_temp_url if converted_temp_url else temp_url,
        }
        self.uploaded_files.append(file_info)
        self.bundled.append(FileWithID(file=file, db_id=file_record.id, name=file_record.filename))

    def add_to_failed_list(self, filename: str, error: str):
        """Add failed file to tracking list"""
        self.failed_files.append({"filename": filename, "error": error})

    def process_individual_file(self, file: UploadFile, temp_file_path: Optional[str] = None) -> bool:
        logger.info(f"Processing file={file.filename}, "f"handler={type(file_handler).__name__}")
        converted_file_key = None
        try:
            if not file.filename:
                self.add_to_failed_list("unknown", "No filename provided")
                return False

            # FIX: define filename early so it always exists
            filename = file.filename

            # Upload to storage
            s3_key = self.upload_single_file_to_storage(file)
            if not s3_key:
                self.add_to_failed_list(file.filename, "Failed to upload file to storage")
                return False

            if (
                not self.category_uuid
                and temp_file_path
                and file.filename.lower().endswith((".pdf", ".xlsx", ".xls", ".csv"))
            ):
                try:
                    detector = GetDocumentCategoryID(
                        temp_file_path,
                        self.get_category_str(),
                        filename=file.filename
                    )
                    category_result = detector.get_category_id()

                    if category_result and hasattr(category_result, "category_id"):
                        self.category_uuid = UUID(str(category_result.category_id))
                        category_obj = get_category_by_id(self.category_uuid)
                        self.category = category_obj.name
                        logger.info(
                            f"Auto-detected category: {self.category} "
                            f"({self.category_uuid}) for file {file.filename}"
                        )
                except Exception as e:
                    logger.warning(f"Category detection failed: {e}", exc_info=True)

            if temp_file_path and file.filename.lower().endswith((".csv", ".xlsx", ".xls")):
                try:
                    pdf_path = temp_file_path.rsplit(".", 1)[0] + ".pdf"

                    logger.info(f"Converting {temp_file_path} → {pdf_path}")

                    convert_table_to_pdf(temp_file_path, pdf_path)

                    if not os.path.exists(pdf_path):
                        raise RuntimeError("PDF not created")

                    converted_file_key = file_handler.save_local_file(
                        pdf_path,
                        self.user_id
                    )

                    logger.info(f"Converted file key = {converted_file_key}")

                except Exception as e:
                    logger.warning(
                        f"Conversion failed for {file.filename}: {e}",
                        exc_info=True
                    )
                    converted_file_key = None

            file_record = self.create_database_record(
                file,
                s3_key,
                filename=filename,
                converted_file_key=converted_file_key,
            )

            if not file_record:
                file_handler.delete_file(s3_key)
                if converted_file_key:
                    file_handler.delete_file(converted_file_key)
                self.add_to_failed_list(file.filename, "Failed to save file information")
                return False

            self.add_to_success_list(file, file_record)
            return True

        except Exception as e:
            logger.error(
                f"Error uploading individual file {file.filename}: {e}",
                exc_info=True
            )
            self.add_to_failed_list(file.filename, str(e))
            return False

    def process_vector_storage(self) -> bool:
        """Process files for vector storage"""
        try:
            documents = process_uploaded_files(
                uploaded_files=self.bundled,
                user_id=self.user_id,
                category=self.category,
            )

            vector_store = milvus_client.get_store("users_db")
            vector_store.add_documents(documents)
            logger.info(
                f"Added {len(documents)} documents to Milvus for user {self.user_id}"
            )
            return True

        except ValueError as validation_error:
            self.cleanup_failed_uploads()
            raise validation_error

    def cleanup_failed_uploads(self):
        """Clean up uploaded files when validation fails"""
        for file_info in self.uploaded_files:
            try:
                file_handler.delete_file(file_info["file_key"])
                soft_delete_file(UUID(file_info["file_id"]), UUID(self.user_id))
            except Exception as cleanup_error:
                logger.error(
                    f"Error cleaning up after validation failure: {cleanup_error}"
                )

    def build_response(self, total_files: int) -> Dict:
        """Build upload response"""
        successful_uploads = len(self.uploaded_files)
        failed_uploads = len(self.failed_files)

        return {
            "success": successful_uploads > 0,
            "message": (
                "All file uploads failed"
                if successful_uploads == 0
                else f"Successfully uploaded {successful_uploads} out of {total_files} files"
            ),
            "total_files": total_files,
            "successful_uploads": successful_uploads,
            "failed_uploads": failed_uploads,
            "uploaded_files": self.uploaded_files,
            "failed_files": self.failed_files if self.failed_files else None,
        }


@cbv(file_service)
class UserFileServiceView:

    @file_service.post("/upload", response_model=MultipleFileUploadResponse)
    def upload_files(
        self,
        files: list[UploadFile] = File(...),
        user_data: dict = Depends(verify_token),
    ):
        """Upload multiple document files to S3 and save details in database"""
        try:
            user_id = user_data["sub"]

            # Initialize upload manager
            upload_manager = FileUploadManager(user_id)

            # Validate input
            upload_manager.validate_files_input(files)

            # Check category rules
            category_error = upload_manager.validate_category_rules(files)
            if category_error:
                return category_error

            # Process each file with auto-category detection
            with TemporaryDirectory() as temp_dir:
                for file in files:
                    # Save file temporarily for category detection (no category provided)
                    temp_file_path = None
                    if file.filename.lower().endswith(('.pdf', '.xlsx', '.xls', '.csv')):
                        temp_file_path = Path(temp_dir) / file.filename
                        try:
                            with open(temp_file_path, "wb") as buffer:
                                file.file.seek(0)
                                shutil.copyfileobj(file.file, buffer)
                            file.file.seek(0)
                        except Exception as temp_error:
                            logger.warning(f"Could not save temp file for category detection: {temp_error}")
                            upload_manager.add_to_failed_list(file.filename, "Failed to save temp file for category detection")
                            continue
                    
                    upload_manager.process_individual_file(file, str(temp_file_path) if temp_file_path else None)

            # Process vector storage if files were uploaded
            if upload_manager.uploaded_files:
                try:
                    upload_manager.process_vector_storage()
                except ValueError as validation_error:
                    return create_response(
                        message=str(validation_error),
                        status=False,
                        error_code=VALIDATION_ERROR_CODE,
                        status_code=400
                    )

            return upload_manager.build_response(len(files))

        except Exception as e:
            logger.error(f"Error uploading files: {e}")
            raise e

    # NOTE: This endpoint is being replaced by /list/v2 which uses the standard pagination response format
    @file_service.get("/list", response_model=FileListResponse)
    def list_user_files(
        self,
        category_id: str = None,
        search: str = Query(None, description="Search files by filename"),
        date: str = Query(None, description="Filter files by specific date (ISO format: YYYY-MM-DD)"),
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=100),
        offset: int = Query(0, ge=0),
        user_data: dict = Depends(verify_token)
    ):
        """Get list of all files uploaded by the user, grouped by date with pagination, search and date filtering"""
        try:
            user_id = user_data["sub"]

            # Convert category_id to UUID if provided
            category_uuid = None
            if category_id:
                try:
                    category_uuid = UUID(category_id)
                except ValueError:
                    raise ValueError(INVALID_CATEGORY_ID_FORMAT)

            # Validate date format if provided
            if date:
                try:
                    from datetime import datetime
                    datetime.fromisoformat(date)
                except ValueError:
                    raise ValueError("Invalid date format. Use YYYY-MM-DD format")

            # Calculate offset from page if offset not explicitly provided
            if offset == 0 and page > 1:
                offset = (page - 1) * page_size

            # Get paginated files from database (optimized - only fetches requested page)
            files_data, total_count = get_files_by_user_id_paginated(
                user_id=UUID(user_id),
                category_id=category_uuid,
                search=search,
                date=date,
                limit=page_size,
                offset=offset
            )
            
            # Calculate total pages
            total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
            
            # Generate presigned URLs for files
            for file_data in files_data:
                try:
                    file_key = file_data.get("file_key")
                    if file_key:
                        temp_url = file_handler.generate_presigned_url(file_key, expiration=1800)
                        converted_temp_url = file_handler.generate_presigned_url(file_data.get("converted_file_key"), expiration=1800) if file_data.get("converted_file_key") else None
                        file_data["temp_url"] = temp_url
                        file_data["converted_temp_url"] = converted_temp_url if converted_temp_url else temp_url
                except Exception as url_error:
                    logger.warning(f"Failed to generate presigned URL for file {file_data.get('id')}: {url_error}")
                    file_data["temp_url"] = None
                    file_data["converted_temp_url"] = None
            
            # Group by date for response
            from collections import defaultdict
            from ai.file_services.utils import get_date_label
            
            date_grouped = defaultdict(list)
            for file_data in files_data:
                created_at_str = file_data.get("created_at")
                if created_at_str:
                    from datetime import datetime
                    created_at = datetime.fromisoformat(created_at_str)
                    date_label, iso_date = get_date_label(created_at)
                    date_grouped[iso_date].append({
                        "date_label": date_label,
                        "file_data": file_data
                    })
            
            # Format response
            date_groups = []
            for date_key in sorted(date_grouped.keys(), reverse=True):
                files_in_date = date_grouped[date_key]
                date_label = files_in_date[0]["date_label"] if files_in_date else date_key
                files_list = [item["file_data"] for item in files_in_date]
                
                date_groups.append({
                    "date": date_key,
                    "date_label": date_label,
                    "files": files_list
                })

            return FileListResponse(
                date_groups=date_groups,
                total_count=total_count,
                total_pages=total_pages,
                message="Files retrieved successfully"
            )

        except Exception as e:
            logger.error(f"Error retrieving files: {e}")
            raise e

    @file_service.get("/list/v2")
    def list_user_files_v2(
        self,
        category_id: str = None,
        search: str = Query(None, description="Search files by filename"),
        date: str = Query(None, description="Filter files by specific date (ISO format: YYYY-MM-DD)"),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        user_data: dict = Depends(verify_token)
    ):
        """Get list of all files uploaded by the user, grouped by date with pagination, search and date filtering (v2 with standard pagination response)"""
        try:
            user_id = user_data["sub"]

            # Convert category_id to UUID if provided
            category_uuid = None
            if category_id:
                try:
                    category_uuid = UUID(category_id)
                except ValueError:
                    raise ValueError(INVALID_CATEGORY_ID_FORMAT)

            # Validate date format if provided
            if date:
                try:
                    from datetime import datetime
                    datetime.fromisoformat(date)
                except ValueError:
                    raise ValueError("Invalid date format. Use YYYY-MM-DD format")

            offset = (page - 1) * page_size

            # Get one extra record to determine if there's a next page
            files_data, total_count = get_files_by_user_id_paginated(
                user_id=UUID(user_id),
                category_id=category_uuid,
                search=search,
                date=date,
                limit=page_size + 1,
                offset=offset
            )

            has_next = len(files_data) > page_size
            if has_next:
                files_data = files_data[:-1]

            # Generate presigned URLs for files
            for file_data in files_data:
                try:
                    file_key = file_data.get("file_key")
                    if file_key:
                        temp_url = file_handler.generate_presigned_url(file_key, expiration=1800)
                        converted_temp_url = file_handler.generate_presigned_url(file_data.get("converted_file_key"), expiration=1800) if file_data.get("converted_file_key") else None
                        file_data["temp_url"] = temp_url
                        file_data["converted_temp_url"] = converted_temp_url if converted_temp_url else temp_url
                except Exception as url_error:
                    logger.warning(f"Failed to generate presigned URL for file {file_data.get('id')}: {url_error}")
                    file_data["temp_url"] = None
                    file_data["converted_temp_url"] = None

            # Group by date for response
            from collections import defaultdict
            from ai.file_services.utils import get_date_label

            date_grouped = defaultdict(list)
            for file_data in files_data:
                created_at_str = file_data.get("created_at")
                if created_at_str:
                    from datetime import datetime
                    created_at = datetime.fromisoformat(created_at_str)
                    date_label, iso_date = get_date_label(created_at)
                    date_grouped[iso_date].append({
                        "date_label": date_label,
                        "file_data": file_data
                    })

            # Format date groups
            date_groups = []
            for date_key in sorted(date_grouped.keys(), reverse=True):
                files_in_date = date_grouped[date_key]
                date_label = files_in_date[0]["date_label"] if files_in_date else date_key
                files_list = [item["file_data"] for item in files_in_date]

                date_groups.append({
                    "date": date_key,
                    "date_label": date_label,
                    "files": files_list
                })

            return create_response(
                message="Files retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={
                    "date_groups": date_groups,
                    "page": page,
                    "page_size": page_size,
                    "has_next": has_next,
                    "total_count": total_count,
                },
            )

        except ValueError as validation_error:
            return create_response(
                message=str(validation_error),
                status=False,
                error_code=VALIDATION_ERROR_CODE,
                status_code=400
            )
        except Exception as e:
            logger.error(f"Error retrieving files (v2): {e}")
            raise e

    @file_service.get("/{file_id}", response_model=dict)
    def get_file_details(self, file_id: str, user_data: dict = Depends(verify_token)):
        """Get details of a specific file"""
        try:
            user_id = user_data["sub"]

            # Convert file_id to UUID
            try:
                file_uuid = UUID(file_id)
            except ValueError:
                return create_response(
                    message=INVALID_FILE_ID_FORMAT,
                    status=False,
                    error_code=SOMETHING_WENT_WRONG,
                    status_code=400
                )

            # Get file from database
            file_data = get_file_by_id(file_uuid, UUID(user_id))

            if not file_data:
                return create_response(
                    message=FILE_NOT_FOUND,
                    status=False,
                    error_code=SOMETHING_WENT_WRONG,
                    status_code=404
                )

            return create_response(
                message="File details retrieved successfully",
                status=True,
                error_code=SUCCESS_CODE,
                data=file_data,
            )

        except Exception as e:
            logger.error(f"Error retrieving file details: {e}")
            return create_response(
                message=went_wrong,
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=500
            )

    def _delete_single_file(self, file_id: str, user_id: UUID) -> tuple[bool, str]:
        """Internal method to delete a single file. Returns (success, error_message)"""
        try:
            file_uuid = UUID(file_id)
        except ValueError:
            return False, INVALID_FILE_ID_FORMAT

        file_data = get_file_by_id(file_uuid, user_id)
        if not file_data:
            return False, FILE_NOT_FOUND

        # Delete from Milvus
        vector_store = milvus_client.get_store("users_db")
        try:
            vector_store.delete(filter=f'file_id == "{str(file_uuid)}"')
            logger.info(f"Deleted documents for file {file_uuid} from Milvus")
        except Exception as e:
            logger.warning(f"Failed to delete from Milvus: {e}")

        # Soft delete from database
        if not soft_delete_file(file_uuid, user_id):
            return False, "Failed to delete file"

        return True, ""

    @file_service.delete("/{file_id}", response_model=dict)
    def delete_file(self, file_id: str, user_data: dict = Depends(verify_token)):
        """Soft delete a file"""
        try:
            success, error = self._delete_single_file(file_id, UUID(user_data["sub"]))

            if not success:
                return create_response(
                    message=error,
                    status=False,
                    error_code=SOMETHING_WENT_WRONG,
                    status_code=404 if error == FILE_NOT_FOUND else 400
                )

            return create_response(
                message="File deleted successfully",
                status=True,
                error_code=SUCCESS_CODE,
                data={"file_id": file_id}
            )

        except Exception as e:
            logger.error(f"Error deleting file: {e}")
            return create_response(
                message=went_wrong,
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=500
            )

    @file_service.post("/bulk-delete", response_model=dict)
    def bulk_delete_files(
        self, request: BulkDeleteRequest, user_data: dict = Depends(verify_token)
    ):
        """Bulk delete multiple files"""
        try:
            file_ids = request.file_ids
            if not file_ids:
                return create_response(
                    message="No file IDs provided",
                    status=False,
                    error_code=VALIDATION_ERROR_CODE,
                    status_code=400
                )

            user_id = UUID(user_data["sub"])
            successful = []
            failed = []

            for fid in file_ids:
                success, error = self._delete_single_file(fid, user_id)
                (successful if success else failed).append(fid if success else {"file_id": fid, "error": error})

            total, success_count, failed_count = len(file_ids), len(successful), len(failed)

            if success_count == 0:
                return create_response(
                    message="All file deletions failed",
                    status=False,
                    error_code=SOMETHING_WENT_WRONG,
                    status_code=500,
                    data={"total": total, "successful": 0, "failed": failed_count, "failed_deletes": failed}
                )

            message = f"Successfully deleted {success_count} out of {total} files"
            if failed_count > 0:
                message += f". {failed_count} failed"

            return create_response(
                message=message,
                status=True,
                error_code=SUCCESS_CODE,
                data={
                    "total": total,
                    "successful": success_count,
                    "failed": failed_count,
                    "successful_deletes": successful,
                    "failed_deletes": failed if failed else None
                }
            )

        except Exception as e:
            logger.error(f"Error in bulk delete: {e}")
            return create_response(
                message=went_wrong,
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=500
            )

    @file_service.get("/download/{file_id}", response_model=FileDownloadResponse)
    def download_file(
        self,
        file_id: str,
        expiration: int = 3600,  # Default 1 hour
        user_data: dict = Depends(verify_token),
    ):
        """Generate a presigned download URL for a file"""
        try:
            user_id = user_data["sub"]

            # Convert file_id to UUID
            try:
                file_uuid = UUID(file_id)
            except ValueError:
                raise ValueError(INVALID_FILE_ID_FORMAT)

            # Get file from database
            file_data = get_file_by_id(file_uuid, UUID(user_id))

            if not file_data:
                raise ValueError(FILE_NOT_FOUND)

            # Use the file_key directly for presigned URL generation
            file_key = file_data["file_key"]

            if not file_key:
                raise ValueError("File key not found")

            # Generate presigned URL
            download_url = file_handler.generate_presigned_url(file_key, expiration)

            if not download_url:
                raise ValueError("Failed to generate download URL")

            return FileDownloadResponse(
                file_id=file_uuid,
                filename=file_data["filename"],
                download_url=download_url,
                expires_in=expiration,
                message="Download URL generated successfully",
            )

        except Exception as e:
            logger.error(f"Error generating download URL: {e}")
            raise e

    @file_service.get("/download-log", response_class=FileResponse)
    def download_log_file(self, user_data: dict = Depends(verify_token)):
        """Download the Prism.log file"""
        try:

            # Path to the log file
            log_file_path = "prism_inspire/logs/Prism.log"

            # Check if file exists
            if not os.path.exists(log_file_path):
                logger.error(f"Log file not found at: {log_file_path}")
                raise ValueError("Log file not found")

            # Return the file as a download
            return FileResponse(
                path=log_file_path,
                filename="Prism.log",
                media_type="text/plain",
                headers={"Content-Disposition": "attachment; filename=Prism.log"},
            )

        except Exception as e:
            logger.error(f"Error downloading log file: {e}")
            raise e
