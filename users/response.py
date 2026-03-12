from typing import Dict, Any, Optional
from starlette.responses import JSONResponse
from datetime import datetime
import enum
from users.rbac.req_resp_parser import ScheduleTypeEnum


def serialize_for_json(obj):
    """Convert objects to JSON-serializable types"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, ScheduleTypeEnum):
        return obj.value
    if hasattr(obj, "__dict__"):
        return {k: serialize_for_json(v) for k, v in obj.__dict__.items()
                if not k.startswith('_')}
    if isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [serialize_for_json(item) for item in obj]
    return obj


# Error codes
SUCCESS_CODE = "000"
SOMETHING_WENT_WRONG = "001"
VALIDATION_ERROR_CODE = "002"
DB_ERROR_CODE = "003"
GEOFENCE_ERROR_CODE = "004"
GEOFENCE_COLLECTION_ERROR_CODE = GEOFENCE_ERROR_CODE
NOT_FOUND = "005"
FORBIDDEN_ERROR_CODE = "006"


def create_response(
    message: str,
    status: bool,
    error_code: str = SUCCESS_CODE,
    description: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    status_code: int = 200
) -> JSONResponse:
    """
    Create a standardized response following the common structure

    Args:
        message: Success or error message
        status: True for success, False for error
        error_code: Error code (000 for success, others for errors)
        description: Additional information about the error/success
        data: Response data payload
        status_code: HTTP status code (defaults to 200)

    Returns:
        JSONResponse with standardized structure
    """
    response_content = {
        "message": message,
        "status": status,
        "error_status": {
            "error_code": error_code,
            "description": description or ""
        },
        "data": serialize_for_json(data) if data is not None else {}
    }

    return JSONResponse(
        content=response_content,
        status_code=status_code
    )
