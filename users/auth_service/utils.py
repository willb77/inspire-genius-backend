import hashlib


def generate_hash(value):
    password_bytes = value.encode('utf-8')
    hash_object = hashlib.sha256(password_bytes)
    return hash_object.hexdigest()


def check_password_hash(password, user_password):
    hash_password = generate_hash(password)
    if hash_password == user_password:
        return True
    return False


def get_full_name(first_name: str = None, last_name: str = None) -> str:
    """
    Combines first_name and last_name into a full name string.

    Args:
        first_name: User's first name (can be None or empty)
        last_name: User's last name (can be None or empty)

    Returns:
        Combined full name as a string, or None if both names are empty/None

    Examples:
        >>> get_full_name("John", "Doe")
        "John Doe"
        >>> get_full_name("John", None)
        "John"
        >>> get_full_name(None, "Doe")
        "Doe"
        >>> get_full_name(None, None)
        None
        >>> get_full_name("", "")
        None
    """
    first = (first_name or "").strip()
    last = (last_name or "").strip()

    full_name = f"{first} {last}".strip()

    return full_name if full_name else None
