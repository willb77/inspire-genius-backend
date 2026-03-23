import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from sqlalchemy import and_, or_, func, desc
from sqlalchemy.exc import IntegrityError
from prism_inspire.db.session import ScopedSession
from prism_inspire.core.log_config import logger
from users.models.license import License, LicenseStatusEnum
from sqlalchemy.orm import joinedload


def create_license(license_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new license
    
    Args:
        license_data: License data dictionary
        created_by: User ID creating the license
        
    Returns:
        License ID if successful, None otherwise
    """
    session = ScopedSession()
    try:
        license_id = uuid.uuid4()

        existing_active_license = session.query(License).filter(
            and_(
                License.organization_id == license_data["organization_id"],
                License.is_deleted == False,
                License.status == LicenseStatusEnum.ACTIVE.value,
                License.end_date >= datetime.now(timezone.utc) # Ensure it's still valid
            )
        ).first()

        if existing_active_license:
            logger.warning(
                f"Organization {license_data['organization_id']} already has an active license."
            )
            return {
                "status": False,
                "message": f"Organization already has an active license valid until {existing_active_license.end_date.date()}."
            }

        
        license_obj = License(
            id=license_id,
            organization_id=license_data["organization_id"],
            subscription_tier=license_data["subscription_tier"],
            start_date=license_data["start_date"],
            end_date=license_data["end_date"],
            status=LicenseStatusEnum.ACTIVE.value
        )
        
        session.add(license_obj)
        session.commit()

        logger.info(f"Created license {license_id} for organization {license_data['organization_id']}")
        return {
            "status": True,
            "message": "License created successfully.",
            "license_id": str(license_id)
        }
        
    except IntegrityError as e:
        session.rollback()
        logger.error(f"Integrity error creating license: {str(e)}")
        return {"status": False, "message": "Database integrity error while creating license."}
    except Exception as e:
        session.rollback()
        logger.error(f"Error creating license: {str(e)}")
        return {"status": False, "message": "Unexpected error occurred while creating license."}
    finally:
        session.close()
        ScopedSession.remove()


def get_license_by_id(license_id: str) -> Optional[License]:
    """
    Get license by ID
    
    Args:
        license_id: License ID
        
    Returns:
        License object or None if not found
    """
    session = ScopedSession()
    try:
        license_obj = session.query(License).filter(
            and_(
                License.id == license_id,
                License.is_deleted == False
            )
        ).first()
        
        return license_obj
        
    except Exception as e:
        logger.error(f"Error getting license by ID: {str(e)}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def update_license(license_id: str, update_data: Dict[str, Any]) -> bool:
    """
    Update license information
    
    Args:
        license_id: License ID
        update_data: Dictionary of fields to update
        
    Returns:
        True if successful, False otherwise
    """
    session = ScopedSession()
    try:
        license_obj = session.query(License).filter(
            and_(
                License.id == license_id,
                License.is_deleted == False
            )
        ).first()
        
        if not license_obj:
            logger.warning(f"License {license_id} not found")
            return False
        
        # Update fields
        for field, value in update_data.items():
            if hasattr(license_obj, field) and value is not None:
                setattr(license_obj, field, value)
        
        license_obj.updated_at = datetime.now(timezone.utc)
        session.commit()
        
        logger.info(f"Updated license {license_id}")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error updating license: {str(e)}")
        return False
    finally:
        session.close()
        ScopedSession.remove()


def get_licenses(
    organization_id: Optional[str] = None,
    status: Optional[str] = None,
    subscription_tier: Optional[str] = None,
    expiring_within_days: Optional[int] = None,
    page: int = 1,
    limit: int = 10
) -> List[License]:
    """
    Get licenses with filtering options
    
    Args:
        organization_id: Filter by organization ID
        status: Filter by license status
        subscription_tier: Filter by subscription tier
        expiring_within_days: Filter licenses expiring within specified days
        page: Page number for pagination
        limit: Number of items per page
        
    Returns:
        List of License objects
    """
    session = ScopedSession()
    try:
        query = session.query(License).options(
            joinedload(License.organization)
        ).filter(License.is_deleted == False)
        
        # Apply filters
        if organization_id:
            query = query.filter(License.organization_id == organization_id)
        
        if status:
            query = query.filter(License.status == status)
        
        if subscription_tier:
            query = query.filter(License.subscription_tier == subscription_tier)
        
        if expiring_within_days:
            now = datetime.now(timezone.utc)  # naive datetime
            expiry_threshold = now + timedelta(days=expiring_within_days)

            query = query.filter(
                and_(
                    License.end_date <= expiry_threshold,
                    License.end_date >= now,
                    License.status == LicenseStatusEnum.ACTIVE.value
                )
            )
                
        # Apply pagination
        offset = (page - 1) * limit
        licenses = query.order_by(License.end_date.asc()).offset(offset).limit(limit).all()
        
        return licenses
        
    except Exception as e:
        logger.error(f"Error getting licenses: {str(e)}")
        return []
    finally:
        session.close()
        ScopedSession.remove()


def get_all_licenses() -> List[License]:
    """
    Get all licenses in the system (for system dashboard)
    
    Returns:
        List of all License objects
    """
    session = ScopedSession()
    try:
        licenses = session.query(License).filter(
            License.is_deleted == False
        ).order_by(desc(License.created_at)).all()
        
        return licenses
        
    except Exception as e:
        logger.error(f"Error getting all licenses: {str(e)}")
        return []
    finally:
        session.close()
        ScopedSession.remove()
