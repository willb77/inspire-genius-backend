from typing import List, Optional, Dict, Any
from uuid import UUID
from sqlalchemy import and_
from prism_inspire.db.session import ScopedSession
from prism_inspire.core.log_config import logger
from ai.models.frontend_text import FrontendText


def get_all_frontend_texts() -> List[FrontendText]:
    """
    Get all frontend texts from the database.
    
    Returns:
        List[FrontendText]: List of all frontend text records
    """
    session = ScopedSession()
    try:
        frontend_texts = session.query(FrontendText).all()
        return frontend_texts
    except Exception as e:
        logger.error(f"Error getting all frontend texts: {e}")
        return []
    finally:
        session.close()
        ScopedSession.remove()


def get_frontend_text_by_id(text_id: UUID) -> Optional[FrontendText]:
    """
    Get a specific frontend text by ID.
    
    Args:
        text_id: UUID of the frontend text
        
    Returns:
        Optional[FrontendText]: Frontend text record if found, None otherwise
    """
    session = ScopedSession()
    try:
        frontend_text = session.query(FrontendText).filter(
            FrontendText.id == text_id
        ).first()
        return frontend_text
    except Exception as e:
        logger.error(f"Error getting frontend text by ID {text_id}: {e}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def get_frontend_texts_by_route(route_key: str) -> List[FrontendText]:
    """
    Get frontend texts by route key.
    
    Args:
        route_key: Route key to filter by
        
    Returns:
        List[FrontendText]: List of frontend text records for the route
    """
    session = ScopedSession()
    try:
        frontend_texts = session.query(FrontendText).filter(
            FrontendText.routeKey == route_key
        ).all()
        return frontend_texts
    except Exception as e:
        logger.error(f"Error getting frontend texts by route {route_key}: {e}")
        return []
    finally:
        session.close()
        ScopedSession.remove()


def get_frontend_texts_by_selector(selector: str) -> List[FrontendText]:
    """
    Get frontend texts by selector.
    
    Args:
        selector: Selector to filter by
        
    Returns:
        List[FrontendText]: List of frontend text records for the selector
    """
    session = ScopedSession()
    try:
        frontend_texts = session.query(FrontendText).filter(
            FrontendText.selector == selector
        ).all()
        return frontend_texts
    except Exception as e:
        logger.error(f"Error getting frontend texts by selector {selector}: {e}")
        return []
    finally:
        session.close()
        ScopedSession.remove()


def get_frontend_text_by_route_and_selector(route_key: str, selector: str) -> Optional[FrontendText]:
    """
    Get a specific frontend text by route key and selector.
    
    Args:
        route_key: Route key to filter by
        selector: Selector to filter by
        
    Returns:
        Optional[FrontendText]: Frontend text record if found, None otherwise
    """
    session = ScopedSession()
    try:
        frontend_text = session.query(FrontendText).filter(
            and_(
                FrontendText.routeKey == route_key,
                FrontendText.selector == selector
            )
        ).first()
        return frontend_text
    except Exception as e:
        logger.error(f"Error getting frontend text by route {route_key} and selector {selector}: {e}")
        return None
    finally:
        session.close()
        ScopedSession.remove()