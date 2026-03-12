from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class FileUploadResponse(BaseModel):
    file_id: UUID = Field(..., description="Unique identifier for the uploaded file")
    filename: str = Field(..., description="Name of the uploaded file")
    file_key: str = Field(..., description="S3 key of the uploaded file")
    file_type: str = Field(..., description="Type/extension of the uploaded file")
    category_id: UUID = Field(..., description="Category ID for the file")
    message: str = Field(..., description="Success message")


class UploadedFileInfo(BaseModel):
    file_id: str = Field(..., description="Unique identifier for the uploaded file")
    filename: str = Field(..., description="Name of the uploaded file")
    file_key: str = Field(..., description="S3 key of the uploaded file")
    file_type: str = Field(..., description="Type/extension of the uploaded file")
    category_id: Optional[str] = Field(None, description="Category ID for the file")
    temp_url: Optional[str] = Field(
        None, description="Temporary presigned URL for accessing the file"
    )
    converted_temp_url: Optional[str] = Field(
        None, description="Temporary presigned URL for accessing the converted file"
    )


class FailedFileInfo(BaseModel):
    filename: str = Field(..., description="Name of the file that failed to upload")
    error: str = Field(..., description="Error message for the failed upload")


class MultipleFileUploadResponse(BaseModel):
    success: bool = Field(..., description="Overall success status")
    message: str = Field(..., description="Summary message")
    total_files: int = Field(..., description="Total number of files attempted")
    successful_uploads: int = Field(
        ..., description="Number of files successfully uploaded"
    )
    failed_uploads: int = Field(
        ..., description="Number of files that failed to upload"
    )
    uploaded_files: List[UploadedFileInfo] = Field(
        ..., description="List of successfully uploaded files"
    )
    failed_files: Optional[List[FailedFileInfo]] = Field(
        None, description="List of files that failed to upload"
    )


class FileInfo(BaseModel):
    id: str = Field(..., description="Unique identifier for the file")
    filename: str = Field(..., description="Name of the file")
    file_key: str = Field(..., description="S3 key of the file")
    converted_file_key : Optional[str] = Field(None, description="S3 key of the converted file")    
    file_type: str = Field(..., description="Type/extension of the file")
    created_at: Optional[str] = Field(None, description="File upload timestamp")
    file_uuid: Optional[str] = Field(None, description="File UUID")
    category_id: Optional[str] = Field(None, description="Category ID for the file")
    category_name: Optional[str] = Field(None, description="Category name for the file")
    temp_url: Optional[str] = Field(
        None, description="Temporary presigned URL for file access"
    )
    converted_temp_url: Optional[str] = Field(
        None, description="Temporary presigned URL for converted file access"
    )


class DateGroupedFiles(BaseModel):
    date_label: str = Field(..., description="Human-readable date label (e.g., 'Today', 'Yesterday')")
    date: str = Field(..., description="ISO date string for the group")
    files: List[FileInfo] = Field(..., description="List of files uploaded on this date")


class FileListResponse(BaseModel):
    date_groups: List[DateGroupedFiles] = Field(..., description="Files grouped by date")
    total_count: int = Field(..., description="Total number of files")
    total_pages: Optional[int] = Field(None, description="Total number of pages available")
    message: str = Field(..., description="Response message")


class FileDownloadResponse(BaseModel):
    file_id: UUID = Field(..., description="Unique identifier for the file")
    filename: str = Field(..., description="Name of the file")
    download_url: str = Field(..., description="Presigned download URL")
    expires_in: int = Field(..., description="URL expiration time in seconds")
    message: str = Field(..., description="Success message")


class DeleteFileResponse(BaseModel):
    success: bool = Field(
        ..., description="Indicates if the file deletion was successful"
    )
    message: str = Field(
        ..., description="Message indicating the result of the deletion operation"
    )
    file_id: Optional[UUID] = Field(
        None, description="ID of the deleted file, if applicable"
    )
    filename: Optional[str] = Field(
        None, description="Name of the deleted file, if applicable"
    )


class BulkDeleteRequest(BaseModel):
    file_ids: List[str] = Field(..., description="Array of file IDs to delete")
