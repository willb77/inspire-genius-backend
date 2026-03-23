from datetime import datetime, timedelta



def get_date_label(file_date: datetime) -> tuple[str, str]:
    """
    Get human-readable date label and ISO date string for file grouping.
    
    Args:
        file_date: The file's created_at datetime
        
    Returns:
        Tuple of (human_label, iso_date_string)
    """
    now = datetime.now(file_date.tzinfo if file_date.tzinfo else None)
    today = now.date()
    file_date_only = file_date.date()
    
    days_diff = (today - file_date_only).days
    
    if days_diff == 0:
        return "Today", file_date_only.isoformat()
    elif days_diff == 1:
        return "Yesterday", file_date_only.isoformat()
    elif days_diff <= 7:
        return f"{days_diff} days ago", file_date_only.isoformat()
    elif days_diff <= 30:
        weeks = days_diff // 7
        if weeks == 1:
            return "1 week ago", file_date_only.isoformat()
        else:
            return f"{weeks} weeks ago", file_date_only.isoformat()
    elif days_diff <= 365:
        months = days_diff // 30
        if months == 1:
            return "1 month ago", file_date_only.isoformat()
        else:
            return f"{months} months ago", file_date_only.isoformat()
    else:
        years = days_diff // 365
        if years == 1:
            return "1 year ago", file_date_only.isoformat()
        else:
            return f"{years} years ago", file_date_only.isoformat()