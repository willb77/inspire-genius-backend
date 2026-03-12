import uuid, os, tempfile

from sqlalchemy.orm import joinedload

from ai.models.files import File  # Added Report
from prism_inspire.core.log_config import logger
from prism_inspire.db.session import ScopedSession
from sqlalchemy import text
from typing import List, Dict
from datetime import datetime, timedelta
from ai.file_services.utils import get_date_label
from collections import defaultdict
from prism_inspire.core.file_utils import S3_BUCKET, file_handler
from ai.models.chat import ChatMessage
from botocore.exceptions import ClientError

def group_files_by_date(files: List[File]) -> Dict[str, List[Dict]]:
    """
    Group files by their upload date.
    
    Args:
        files: List of File objects
        
    Returns:
        Dictionary with date labels as keys and lists of file data as values
    """
    date_groups = defaultdict(list)
    
    for file in files:
        if file.created_at:
            date_label, iso_date = get_date_label(file.created_at)
            
            file_data = {
                "id": str(file.id),
                "filename": file.filename,
                "file_key": file.file_key,
                "file_type": file.file_type,
                "created_at": file.created_at.isoformat() if file.created_at else None,
                "file_uuid": str(file.file_uuid) if file.file_uuid else None,
                "category_id": str(file.category_id) if file.category_id else None,
                "category_name": file.category.name if file.category else None,
            }
            
            # Use iso_date as the key for consistent sorting
            date_groups[iso_date].append({
                "date_label": date_label,
                "file_data": file_data
            })
    
    return dict(date_groups)


def create_file_record(user_id, filename, file_type, file_key, category_id=None, converted_file_key=None):
    """Create a new file record in the database"""
    try:
        session = ScopedSession()

        file_record = File(
            id=uuid.uuid4(),
            filename=filename,
            file_uuid=uuid.uuid4(),
            file_type=file_type,
            file_key=file_key,
            category_id=category_id,
            user_id=user_id,
            is_deleted=False,
            converted_file_key=converted_file_key
        )

        session.add(file_record)
        session.commit()
        session.refresh(file_record)

        logger.info(f"File record created successfully for user {user_id}: {filename}")
        return file_record

    except Exception as e:
        session.rollback()
        logger.error(f"Error creating file record: {e}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def get_files_by_user_id(user_id, category_id=None):
    """Get all files for a specific user, optionally filtered by category, grouped by date only"""
    try:
        session = ScopedSession()

        query = (
            session.query(File)
            .options(joinedload(File.category))
            .filter(File.user_id == user_id, File.is_deleted.is_(False))
        )

        if category_id:
            query = query.filter(File.category_id == category_id)

        files = query.order_by(File.created_at.desc()).all()

        # Group files by date only (no category grouping)
        date_grouped_files = group_files_by_date(files)
        
        # Sort dates (most recent first)
        sorted_dates = sorted(date_grouped_files.keys(), reverse=True)
        
        date_groups = []
        for date_key in sorted_dates:
            files_in_date = date_grouped_files[date_key]
            
            # All files in the same date group will have the same date_label
            date_label = files_in_date[0]["date_label"] if files_in_date else date_key
            
            # Extract just the file data
            files_data = [item["file_data"] for item in files_in_date]
            
            date_groups.append({
                "date_label": date_label,
                "date": date_key,
                "files": files_data
            })

        return date_groups

    except Exception as e:
        logger.error(f"Error retrieving files for user {user_id}: {e}")
        return []
    finally:
        session.close()
        ScopedSession.remove()


def get_files_by_user_id_paginated(user_id, category_id=None, search=None, date=None, limit=10, offset=0):
    """
    Get paginated files for a specific user with total count.
    Optimized to fetch only requested page from database.

    Args:
        user_id: User UUID
        category_id: Optional category filter
        search: Optional search string to filter by filename
        date: Optional date string (YYYY-MM-DD) to filter files by specific date
        limit: Number of files to return
        offset: Number of files to skip

    Returns:
        Tuple of (files_list, total_count)
    """
    try:
        session = ScopedSession()

        # Base query for filtering
        base_query = (
            session.query(File)
            .filter(File.user_id == user_id, File.is_deleted.is_(False))
        )

        if category_id:
            base_query = base_query.filter(File.category_id == category_id)

        # Apply search filter (case-insensitive partial match)
        if search:
            base_query = base_query.filter(File.filename.ilike(f"%{search}%"))

        # Apply date filter (filter files created on specific date)
        if date:
            from datetime import datetime
            date_obj = datetime.fromisoformat(date)
            # Filter files created on the specified date (from 00:00:00 to 23:59:59)
            start_of_day = date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = date_obj.replace(hour=23, minute=59, second=59, microsecond=999999)
            base_query = base_query.filter(File.created_at >= start_of_day, File.created_at <= end_of_day)

        # Get total count (optimized - just counts, no data fetching)
        total_count = base_query.count()

        # Get paginated files with category info
        files = (
            base_query
            .options(joinedload(File.category))
            .order_by(File.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

        # Convert to list of dicts with all needed info
        files_data = []
        for file in files:
            files_data.append({
                "id": str(file.id),
                "filename": file.filename,
                "file_key": file.file_key,
                "file_type": file.file_type,
                "created_at": file.created_at.isoformat() if file.created_at else None,
                "file_uuid": str(file.file_uuid) if file.file_uuid else None,
                "category_id": str(file.category_id) if file.category_id else None,
                "category_name": file.category.name if file.category else None,
                "converted_file_key": file.converted_file_key,
            })

        return files_data, total_count

    except Exception as e:
        logger.error(f"Error retrieving paginated files for user {user_id}: {e}")
        return [], 0
    finally:
        session.close()
        ScopedSession.remove()


def get_file_by_id(file_id, user_id):
    """Get a specific file by ID for a user"""
    try:
        session = ScopedSession()

        file = (
            session.query(File)
            .filter(
                File.id == file_id, File.user_id == user_id, File.is_deleted.is_(False)
            )
            .first()
        )

        if file:
            return {
                "id": str(file.id),
                "filename": file.filename,
                "file_key": file.file_key,
                "file_type": file.file_type,
                "category_id": str(file.category_id) if file.category_id else None,
                "created_at": file.created_at.isoformat() if file.created_at else None,
                "file_uuid": str(file.file_uuid) if file.file_uuid else None,
            }

        return None

    except Exception as e:
        logger.error(f"Error retrieving file {file_id} for user {user_id}: {e}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def soft_delete_file(file_id, user_id):
    """Soft delete a file (mark as deleted)"""
    try:
        session = ScopedSession()

        file = (
            session.query(File)
            .filter(
                File.id == file_id, File.user_id == user_id, File.is_deleted.is_(False)
            )
            .first()
        )

        if file:
            file.is_deleted = True
            session.commit()
            logger.info(f"File {file_id} soft deleted for user {user_id}")
            return True

        return False

    except Exception as e:
        session.rollback()
        logger.error(f"Error soft deleting file {file_id} for user {user_id}: {e}")
        return False
    finally:
        session.close()
        ScopedSession.remove()


def get_file_category_by_file_id(file_id, user_id=None):
    """Get file category information by file ID, optionally verify user access"""
    try:
        session = ScopedSession()

        query = (
            session.query(File)
            .options(joinedload(File.category))
            .filter(File.id == file_id, File.is_deleted.is_(False))
        )

        file = query.first()

        if not file:
            logger.error(f"File {file_id} not found")
            return None

        # If user_id is provided, verify the user owns the file
        if user_id and file.user_id != user_id:
            logger.error(f"User {user_id} does not have access to file {file_id}")
            return None

        # Return just the category name
        return file.category.name if file.category else None

    except Exception as e:
        logger.error(f"Error retrieving category for file {file_id}: {e}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


async def get_filenames_for_files(file_ids: List[str], user_id: str) -> Dict[str, str]:
    """
    Retrieve filenames for a list of file IDs.
    
    Args:
        file_ids: List of file IDs to retrieve filenames for
        user_id: User ID to verify access
        
    Returns:
        Dictionary mapping file_id -> filename
    """
    from prism_inspire.db.session import SessionLocal
    from sqlalchemy import text
    
    if not file_ids:
        return {}
    
    session = SessionLocal()
    try:
        # Prepare placeholders for SQL IN clause
        placeholders = ",".join([f":id{i}" for i in range(len(file_ids))])
        params = {f"id{i}": fid for i, fid in enumerate(file_ids)}
        params["user_id"] = user_id
        
        stmt = text(f"""
            SELECT id, filename 
            FROM files 
            WHERE id IN ({placeholders}) 
            AND user_id = :user_id
            AND is_deleted = false
        """)
        
        result = session.execute(stmt, params)
        
        # Convert results to dictionary
        # filename_map = {str(row[0]): row[1] for row in result}
        filenames = [row[1] for row in result]
        return ", ".join(filenames)
        
    except Exception as e:
        print(f"Error fetching filenames: {e}")
        return {}
    finally:
        session.close()


async def get_report_str_for_files(file_ids: List[str]) -> Dict[str, str]:
    """
    Retrieve report_str for PRISM report files only.
    report_str only exists for files with category 'reports'.
    
    Args:
        file_ids: List of file IDs to retrieve reports for
        
    Returns:
        Dictionary mapping file_id -> report_str for report files only
    """
    from prism_inspire.db.session import SessionLocal
    from sqlalchemy import text
    
    if not file_ids:
        return {}
    
    session = SessionLocal()
    try:
        # Prepare placeholders for SQL IN clause
        placeholders = ",".join([f":id{i}" for i in range(len(file_ids))])
        params = {f"id{i}": fid for i, fid in enumerate(file_ids)}
        
        stmt = text(f"""
            SELECT r.file_id, r.report_str 
            FROM reports r
            INNER JOIN files f ON r.file_id = f.id
            WHERE r.file_id IN ({placeholders}) 
            AND r.is_deleted = false
            AND f.is_deleted = false
        """)
        
        result = session.execute(stmt, params)
        
        # Convert results to dictionary
        report_map = {str(row[0]): row[1] for row in result}
        return report_map
        
    except Exception as e:
        print(f"Error fetching report_str: {e}")
        return {}
    finally:
        session.close()

def get_audio_file_path_by_message_id(message_id: str):
    """
    Resolve an audio file path for a given message_id.

    Strategy:
      1. Look up ChatMessage in DB and try common fields that may refer to audio (local path or S3 key).
      2. If a local path is found and exists, return it.
      3. If an S3 key is found, download the object into a temp file and return the temp path.
      4. Otherwise return None.

    This function is defensive and tries several common field names used across the codebase.
    """
    if not message_id:
        return None

    try:
        # Try DB lookup first
        with ScopedSession() as session:
            msg = (
                session.query(ChatMessage)
                .filter(getattr(ChatMessage, "id") == message_id)
                .first()
            )
            if msg:
                local_attrs = ["audio_path", "file_path", "local_path", "path"]
                s3_attrs = ["audio_s3_key", "key"]

                for a in local_attrs:
                    val = getattr(msg, a, None)
                    if val and isinstance(val, str) and os.path.isfile(val):
                        return val

                for a in s3_attrs:
                    key = getattr(msg, a, None)
                    if key and isinstance(key, str):
                        # Attempt to download from S3 into a temp file
                        bucket = S3_BUCKET or os.getenv("S3_BUCKET_NAME")
                        if not bucket:
                            logger.error("get_audio_file_path_by_message_id: S3 bucket not configured")
                            break
                        try:
                            client = file_handler.s3_client
                            obj = client.get_object(Bucket=bucket, Key=key)
                            body = obj.get("Body")
                            if body is None:
                                continue
                            data = body.read()
                            # infer extension from key or content-type / header
                            _, ext = os.path.splitext(key)
                            if not ext:
                                content_type = obj.get("ContentType", "")
                                if "wav" in content_type:
                                    ext = ".wav"
                                elif "pcm" in content_type:
                                    ext = ".pcm"
                                elif "mp3" in content_type:
                                    ext = ".mp3"
                                else:
                                    ext = ".bin"

                            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, prefix=f"{message_id}_")
                            tmp.write(data)
                            tmp.flush()
                            tmp.close()
                            return tmp.name
                        except ClientError as ce:
                            logger.exception("S3 ClientError while fetching key=%s: %s", key, ce)
                        except Exception as e:
                            logger.exception("Error downloading s3 key=%s: %s", key, e)

    except Exception as e:
        logger.exception("Error resolving audio path for message_id=%s: %s", message_id, e)

    # As a fallback, also check common filesystem locations by message_id
    candidates = [
        f"/tmp/audio/{message_id}.wav",
        f"/tmp/audio/{message_id}.mp3",
        f"/var/tmp/audio/{message_id}.wav",
        f"./audio_output/{message_id}.wav",
        f"./audio_output/{message_id}.mp3",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    return None