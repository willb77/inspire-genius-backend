import re
from typing import Optional, Tuple


def validate_name(name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate user name field

    Args:
        name: User's name

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not name:
        return False, "Name is required"

    # Remove extra whitespace
    name = name.strip()

    if not validate_field_pattern(name, 'name'):
        error_msg = (
            "Name can only contain "
            "letters, spaces, hyphens, and apostrophes, "
            "and must be properly formatted"
        )
        return False, error_msg

    return True, None


def validate_mobile_number(
    mobile_number: Optional[str]
) -> Tuple[bool, Optional[str]]:
    """
    Validate mobile number field

    Args:
        mobile_number: User's mobile number (optional)

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not mobile_number:
        return True, None  # Mobile number is optional

    # Remove extra whitespace
    mobile_number = mobile_number.strip()

    if not validate_field_pattern(mobile_number, 'mobile'):
        error_msg = (
            "Mobile number can only contain "
            "digits, spaces, hyphens, parentheses, and plus sign, "
            "and must be properly formatted"
        )
        return False, error_msg

    # Extract only digits to check minimum digit count
    digits_only = re.sub(r"[^\d]", "", mobile_number)
    if len(digits_only) < 10:
        return False, "Mobile number must contain at least 10 digits"

    if len(digits_only) > 15:
        return False, "Mobile number cannot contain more than 15 digits"

    return True, None


def validate_profile_data(
    name: str, mobile_number: Optional[str] = None,
    role: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate complete profile data

    Args:
        name: User's name
        mobile_number: User's mobile number (optional)
        role: User's role (optional)

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Validate name
    is_valid, error_msg = validate_name(name)
    if not is_valid:
        return False, error_msg

    # Validate mobile number
    is_valid, error_msg = validate_mobile_number(mobile_number)
    if not is_valid:
        return False, error_msg

    # Validate role
    is_valid, error_msg = validate_role(role)
    if not is_valid:
        return False, error_msg

    return True, None


def sanitize_name(name: str) -> str:
    """
    Sanitize and format name field

    Args:
        name: Raw name input

    Returns:
        Sanitized name
    """
    if not name:
        return ""

    # Remove extra whitespace and normalize
    name = " ".join(name.split())

    # Capitalize each word properly
    # Handle special cases like O'Connor, McDonald, etc.
    words = []
    for word in name.split():
        if "'" in word:
            # Handle names like O'Connor
            parts = word.split("'")
            formatted_parts = [part.capitalize() for part in parts]
            words.append("'".join(formatted_parts))
        elif word.lower().startswith("mc") and len(word) > 2:
            # Handle names like McDonald
            words.append("Mc" + word[2:].capitalize())
        else:
            words.append(word.capitalize())

    return " ".join(words)


def sanitize_mobile_number(mobile_number: Optional[str]) -> Optional[str]:
    """
    Sanitize mobile number field

    Args:
        mobile_number: Raw mobile number input

    Returns:
        Sanitized mobile number or None
    """
    if not mobile_number:
        return None

    # Remove extra whitespace
    mobile_number = mobile_number.strip()

    if not mobile_number:
        return None

    # Remove any extra spaces between digits
    mobile_number = re.sub(r"\s+", " ", mobile_number)

    return mobile_number


# File upload validation
def validate_file_upload(
    file, max_size_mb: int = 5
) -> Tuple[bool, Optional[str]]:
    """
    Validate uploaded file

    Args:
        file: UploadFile object
        max_size_mb: Maximum file size in MB

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not file or not file.filename:
        return False, "No file provided"

    # Check file type
    allowed_types = ['image/jpeg', 'image/png', 'image/jpg']
    if file.content_type not in allowed_types:
        return False, "Invalid file type. Only JPEG and PNG images are allowed"

    # Check file extension
    allowed_extensions = ['.jpg', '.jpeg', '.png']
    file_extension = file.filename.lower().split('.')[-1]
    if f'.{file_extension}' not in allowed_extensions:
        error_msg = (
            "Invalid file extension. "
            "Only .jpg, .jpeg, and .png files are allowed"
        )
        return False, error_msg

    # Check file size
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Reset to beginning

    max_size_bytes = max_size_mb * 1024 * 1024
    if file_size > max_size_bytes:
        return False, f"File size too large. Maximum size is {max_size_mb}MB"

    # Check minimum file size (to avoid empty files)
    if file_size < 1024:  # 1KB minimum
        return False, "File is too small. Minimum size is 1KB"

    return True, None


# Common validation patterns
VALIDATION_PATTERNS = {
    'name': r"^[a-zA-Z\s\-'\.]+$",
    'mobile': r"^[\+]?[\d\s\-\(\)]+$",
    'email': r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
}


def validate_field_pattern(value: str, pattern_name: str) -> bool:
    """
    Validate field against predefined patterns

    Args:
        value: Value to validate
        pattern_name: Name of pattern from VALIDATION_PATTERNS

    Returns:
        True if valid, False otherwise
    """
    if pattern_name not in VALIDATION_PATTERNS:
        return False

    pattern = VALIDATION_PATTERNS[pattern_name]
    return bool(re.match(pattern, value))


def validate_role(role: Optional[str]) -> Tuple[bool, Optional[str]]:
    """
    Validate user role field

    Args:
        role: User's role (optional)

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not role:
        return True, None  # Role is optional

    # Remove extra whitespace
    role = role.strip()

    # Check if role is one of the allowed values
    allowed_roles = ["Administrator", "user"]
    if role not in allowed_roles:
        error_msg = f"Role must be one of: {', '.join(allowed_roles)}"
        return False, error_msg

    return True, None
