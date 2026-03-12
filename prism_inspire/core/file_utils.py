import os
import uuid
import boto3, mimetypes
import pandas as pd
from typing import Optional, Tuple
from fastapi import UploadFile
from botocore.exceptions import ClientError, NoCredentialsError, BotoCoreError
from botocore.config import Config
from prism_inspire.core.log_config import logger
from prism_inspire.core.config import settings
from typing import Dict
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

_S3_CLIENT_NOT_AVAILABLE_MSG = (
    "S3 client is not initialized. File operations will fail."
)
S3_REGION: Optional[str] = os.environ.get("S3_REGION") or os.environ.get("LOCATION_AWS_REGION")
S3_BUCKET: Optional[str] = os.environ.get("S3_BUCKET") or os.environ.get("S3_BUCKET_NAME")


class S3FileHandler:
    """Handles file storage operations (upload, delete, URL generation) with AWS S3."""

    def __init__(self, prefix: str = None):
        """Initializes the S3 client and configuration."""
        self.bucket_name = settings.S3_BUCKET_NAME
        self.region = settings.AWS_REGION
        self.prefix = prefix if prefix else settings.S3_DOCUMENTS_PREFIX
        self.max_size = 10 * 1024 * 1024  # 10MB default

        # Allowed content types for various documents
        self.allowed_content_types: Dict[str, str] = {
            'pdf': 'application/pdf',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'doc': 'application/msword',
            'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'ppt': 'application/vnd.ms-powerpoint',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'xls': 'application/vnd.ms-excel',
            'csv': 'text/csv',
            'txt': 'text/plain',
            'json': 'application/json',
            'md': 'text/markdown',
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'pcm': 'audio/pcm',
            'wav': 'audio/wav',
        }

        # Initialize S3 client
        try:
            client_kwargs = {}
            # prefer settings but fall back to environment S3_REGION if needed
            self.region = self.region or S3_REGION
            if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
                client_kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
                client_kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
            # include session token if present
            if getattr(settings, "AWS_SESSION_TOKEN", None):
                client_kwargs["aws_session_token"] = settings.AWS_SESSION_TOKEN
            if self.region:
                client_kwargs["region_name"] = self.region

            self.s3_client = boto3.client("s3", **client_kwargs)
            self._verify_bucket_access()
        except NoCredentialsError:
            logger.error("AWS credentials not found. S3 operations will fail.")
            self.s3_client = None
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")
            self.s3_client = None

    def _sanitize_for_metadata(self, value: str) -> str:
        """
        Sanitize a string for S3 metadata.
        S3 metadata values must be ASCII.
        """
        try:
             value.encode('ascii')
             return value
        except UnicodeEncodeError:
            # If it contains non-ASCII, URL-encode it
            from urllib.parse import quote
            return quote(str(value))

    def _verify_bucket_access(self):
        """Verify that the configured S3 bucket is accessible."""
        if not self.bucket_name:
            logger.warning("S3_BUCKET_NAME not configured. File uploads will fail.")
            return
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"Successfully connected to S3 bucket: {self.bucket_name}")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                logger.error(f"S3 bucket '{self.bucket_name}' does not exist.")
            elif error_code == '403':
                logger.error(f"Access denied to S3 bucket '{self.bucket_name}'.")
            else:
                logger.error(f"Error accessing S3 bucket '{self.bucket_name}': {e}")
            self.s3_client = None  # Invalidate client on bucket error

    def _validate_file_type(self, file: UploadFile) -> tuple[bool, str]:
        """
        Validates the file's existence and content type.

        Args:
            file: The file to validate.

        Returns:
            A tuple containing a boolean (True if valid) and an error message.
        """
        if not file or not file.filename:
            return False, "No file provided."

        if file.content_type not in self.allowed_content_types.values():
            allowed_exts = ", ".join(self.allowed_content_types.keys())
            return False, f"Unsupported file type. Allowed types: {allowed_exts}."

        return True, ""

    def save_file(self, file: UploadFile, user_id: str = "N/A") -> Optional[str]:
        """
        Validates, checks size, and uploads a file to S3.

        Args:
            file: The file to upload.
            user_id: The ID of the user uploading the file, for metadata.

        Returns:
            The S3 key if the upload is successful, otherwise None.
        """
        if not self.s3_client:
            logger.error(_S3_CLIENT_NOT_AVAILABLE_MSG)
            return None

        # Validate file type
        is_valid, error_msg = self._validate_file_type(file)
        if not is_valid:
            logger.error(f"File validation failed: {error_msg}")
            return None

        try:
            # Check file size before reading the whole content
            file.file.seek(0, os.SEEK_END)
            file_size = file.file.tell()
            if file_size > self.max_size:
                logger.error(f"File size {file_size} exceeds max limit of {self.max_size}.")
                return None
            file.file.seek(0)  # Reset file pointer

            # Generate a unique key for the S3 object
            file_extension = os.path.splitext(file.filename)[1]
            s3_key = f"{self.prefix}/{user_id}_{uuid.uuid4()}{file_extension}"

            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=file.file,
                ContentType=file.content_type,
                Metadata={
                    'user_id': self._sanitize_for_metadata(str(user_id)),
                    'original_filename': self._sanitize_for_metadata(file.filename)
                },
            )

            logger.info(f"File uploaded successfully to S3 with key: {s3_key}")
            return s3_key

        except ClientError as e:
            logger.exception(f"AWS S3 error while uploading file: {e}")
            return None
        except Exception as e:
            logger.exception(f"An unexpected error occurred during file upload: {e}")
            return None
        
    def save_file_bytes(self, file_bytes: bytes, key: str, user_id: str) -> Optional[str]:
        
        if not self.s3_client:
            logger.error(_S3_CLIENT_NOT_AVAILABLE_MSG)
            return None
        s3_key = f"{self.prefix}/{key}"
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=file_bytes,
                Metadata={
                    'user_id': user_id,
                }
            )
        except ClientError as e:
            logger.exception(f"AWS S3 error while uploading file bytes: {e}")
            return None
        except Exception as e:
            logger.exception(f"An unexpected error occurred during file upload: {e}")
            return None
        return s3_key

    def delete_file(self, s3_key: str) -> bool:
        """
        Deletes a file from the S3 bucket.

        Args:
            s3_key: The S3 key of the file to delete.

        Returns:
            True if deletion was successful or key was empty, False otherwise.
        """
        if not s3_key:
            return True  # Nothing to delete

        if not self.s3_client:
            logger.error(_S3_CLIENT_NOT_AVAILABLE_MSG)
            return False

        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            logger.info(f"File deleted successfully from S3: {s3_key}")
            return True
        except ClientError as e:
            logger.exception(f"AWS S3 error deleting file {s3_key}: {e}")
            return False

    def get_public_url(self, s3_key: str) -> Optional[str]:
        """
        Generates a direct public URL for a file in S3.
        Note: The object must have public read permissions.

        Args:
            s3_key: The S3 key of the file.

        Returns:
            The public URL string or None if the key is invalid.
        """
        if not s3_key or not self.bucket_name or not self.region:
            return None
            
        return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"


    def generate_presigned_url(self, s3_key: str, expiration: int = 3600) -> Optional[str]:
        """
        Generates a presigned URL for temporary, secure access to a private file.

        Args:
            s3_key: The S3 key of the file.
            expiration: URL validity time in seconds (default: 1 hour).

        Returns:
            A presigned URL string or None if an error occurs.
        """
        if not self.s3_client:
            logger.error(_S3_CLIENT_NOT_AVAILABLE_MSG)
            return None
        if not s3_key:
            return None
        try:
            return self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=expiration,
            )
        except ClientError as e:
            logger.exception(f"AWS S3 error generating presigned URL for {s3_key}: {e}")
            return None
        
    def save_local_file(self, local_path: str, user_id: str) -> Optional[str]:
        """
        Upload a locally created file (ex: converted PDF) to S3
        and return the S3 key.
        """
        if not self.s3_client:
            logger.error(_S3_CLIENT_NOT_AVAILABLE_MSG)
            return None

        if not local_path or not os.path.exists(local_path):
            logger.error(f"Local file does not exist: {local_path}")
            return None

        try:
            filename = os.path.basename(local_path)
            extension = os.path.splitext(filename)[1].lower()

            # Guess content type (pdf → application/pdf)
            content_type, _ = mimetypes.guess_type(filename)
            content_type = content_type or "application/octet-stream"

            # Generate S3 key
            s3_key = f"{self.prefix}/{user_id}_converted_{uuid.uuid4()}{extension}"
            logger.info(f"save_local_file() called with path={local_path}")

            with open(local_path, "rb") as f:
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=f,
                    ContentType=content_type,
                    Metadata={
                        "user_id": self._sanitize_for_metadata(str(user_id)),
                        "converted_from": self._sanitize_for_metadata(filename),
                    },
                )

            logger.info(f"Returning converted S3 key: {s3_key}")
            return s3_key

        except ClientError as e:
            logger.exception(f"AWS S3 error uploading converted file: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error uploading local file: {e}")
            return None
        
    def get_object_bytes(self, s3_key: str) -> Optional[bytes]:
        """
        Retrieves the bytes of an object from S3.

        Args:
            s3_key: The S3 key of the file.

        Returns:
            The file content as bytes or None if an error occurs.
        """
        if not self.s3_client:
            logger.error(_S3_CLIENT_NOT_AVAILABLE_MSG)
            return None
        if not s3_key:
            return None

        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            return response['Body'].read()
        except ClientError as e:
            logger.exception(f"AWS S3 error retrieving object {s3_key}: {e}")
            return None

    def upload_bytes(
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Upload bytes to S3. Returns (success, key) on success; raises on failure.
        """

        region = S3_REGION
        client_kwargs = {}
        if aws_access_key_id and aws_secret_access_key:
            client_kwargs["aws_access_key_id"] = aws_access_key_id
            client_kwargs["aws_secret_access_key"] = aws_secret_access_key
        if region:
            client_kwargs["region_name"] = region
        try:
            client = boto3.client("s3", **client_kwargs)
            client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
            logger.info("Uploaded to s3://%s/%s (size=%d)", bucket, key, len(data) if data else 0)
            return True, key
        except (BotoCoreError, ClientError) as exc:
            logger.exception("S3 upload failed for s3://%s/%s: %s", bucket, key, exc)
            raise

# Backward compatibility class for local file storage
class LocalFileUploadHandler:
    """Handle file uploads for profile photos using local storage (fallback)"""

    def __init__(self, upload_dir: str = "uploads/profile_photos"):
        self.upload_dir = upload_dir
        self.allowed_types = ['image/jpeg', 'image/png', 'image/jpg']
        self.max_size = 5 * 1024 * 1024  # 5MB

        # Create upload directory if it doesn't exist
        os.makedirs(upload_dir, exist_ok=True)
        logger.warning(
            "Using local file storage. Consider configuring S3 for production."
        )

    def validate_file(self, file: UploadFile) -> tuple[bool, str]:
        """Validate uploaded file"""
        if not file or not file.filename:
            return False, "No file provided"

        if file.content_type not in self.allowed_types:
            return False, (
                "Invalid file type. Only JPEG and PNG images are allowed"
            )

        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)

        if file_size > self.max_size:
            return False, "File size too large. Maximum size is 5MB"

        return True, ""

    def save_file(self, file: UploadFile, user_id: str) -> Optional[str]:
        """Save file locally"""
        try:
            is_valid, _ = self.validate_file(file)
            if not is_valid:
                return None

            file_extension = os.path.splitext(file.filename)[1]
            unique_filename = f"{user_id}_{uuid.uuid4()}{file_extension}"
            file_path = os.path.join(self.upload_dir, unique_filename)

            with open(file_path, "wb") as buffer:
                content = file.file.read()
                buffer.write(content)

            return unique_filename
        except Exception as e:
            logger.exception(f"Error saving file locally: {e}")
            return None

    def delete_file(self, filename: str) -> bool:
        """Delete local file"""
        try:
            if not filename:
                return True

            file_path = os.path.join(self.upload_dir, filename)
            if os.path.exists(file_path):
                os.remove(file_path)
            return True
        except Exception as e:
            logger.exception(
                f"Error deleting local file {filename}: {e}"                
            )
            return False

    def get_file_url(self, filename: str) -> Optional[str]:
        """Get local file URL"""
        if not filename:
            return None

        file_path = os.path.join(self.upload_dir, filename)
        if os.path.exists(file_path):
            return f"/uploads/profile_photos/{filename}"
        return None


def create_file_handler(prefix: str | None = None):
    """Create appropriate file handler based on configuration."""
    if settings.S3_BUCKET_NAME:
        return S3FileHandler(prefix=prefix)
    logger.warning("S3_BUCKET_NAME not configured. Using local storage.")
    return LocalFileUploadHandler()



file_handler = create_file_handler()


class BackblazeFileHandler:
    """Handles file operations for Backblaze B2."""

    def __init__(self):
        self.bucket_name = settings.B2_BUCKET_NAME
        self.endpoint_url = settings.B2_ENDPOINT_URL
        self.key_id = settings.B2_KEY_ID.strip() if settings.B2_KEY_ID else None
        self.application_key = settings.B2_APPLICATION_KEY.strip() if settings.B2_APPLICATION_KEY else None
        
        try:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=self.endpoint_url,
                region_name='us-east-1',
                aws_access_key_id=self.key_id,
                aws_secret_access_key=self.application_key,
                config=Config(signature_version='s3v4', 
                              s3={'addressing_style': 'path'})
            )
        except Exception as e:
            logger.error(f"Failed to initialize Backblaze client: {e}")
            self.s3_client = None

    def upload_log(self, content: str, filename: str):
        """Uploads a log string to Backblaze B2."""
        if not self.s3_client:
            logger.warning("Backblaze client not initialized. Skipping upload.")
            return

        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=filename,
                Body=content.encode('utf-8'),
                ContentType='text/plain'
            )
            logger.debug(f"Log uploaded to Backblaze: {filename}")
        except Exception as e:
            logger.error(f"Failed to upload log to Backblaze: {e}")


backblaze_handler = BackblazeFileHandler()
