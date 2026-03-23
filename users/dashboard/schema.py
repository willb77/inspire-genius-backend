from typing import Dict, Any, List
from datetime import datetime, timedelta, timezone
from sqlalchemy import and_, func
from ai.models.agents import Category
from ai.models.files import File
from prism_inspire.db.session import ScopedSession
from prism_inspire.core.log_config import logger
from users.models.user import Organization, Business, UserProfile, Users
from users.models.license import License, LicenseStatusEnum


def get_organization_stats() -> Dict[str, int]:
    """
    Get organization statistics
    
    Returns:
        Dictionary with organization statistics
    """
    session = ScopedSession()
    try:
        # Total organizations
        total_orgs = session.query(Organization).filter(
            Organization.is_deleted == False
        ).count()
        
        active_orgs = session.query(Organization).filter(
            and_(
                Organization.is_deleted == False,
                Organization.status == True
            )
        ).count()
        
        return {
            "total_organizations": total_orgs,
            "active_organizations": active_orgs,
            "inactive_organizations": total_orgs - active_orgs
        }
        
    except Exception as e:
        logger.error(f"Error getting organization stats: {str(e)}")
        return {
            "total_organizations": 0,
            "active_organizations": 0,
            "inactive_organizations": 0
        }
    finally:
        session.close()
        ScopedSession.remove()


def get_business_stats() -> Dict[str, Any]:
    """
    Get business statistics (active vs inactive and type breakdown - compulsory type)
    """
    session = ScopedSession()
    try:
        # Total businesses
        total_businesses = session.query(Business).filter(
            Business.is_deleted == False
        ).count()

        # Active businesses
        active_businesses = session.query(Business).filter(
            and_(
                Business.is_deleted == False,
                Business.is_active == True
            )
        ).count()

        # Businesses by type (compulsory)
        business_types = session.query(
            Business.business_type,
            func.count(Business.id).label('count')
        ).filter(
            Business.is_deleted == False
        ).group_by(Business.business_type).all()
        businesses_by_type = {bt.business_type.value if hasattr(bt.business_type, "value") else bt.business_type: bt.count for bt in business_types}
        
        # Active businesses by type
        active_by_type = session.query(
            Business.business_type,
            func.count(Business.id).label('count')
        ).filter(
            and_(
                Business.is_deleted == False,
                Business.is_active == True
            )
        ).group_by(Business.business_type).all()
        active_by_type_dict = {bt.business_type.value if hasattr(bt.business_type, "value") else bt.business_type: bt.count for bt in active_by_type}


        # Inactive businesses by type
        inactive_by_type = session.query(
            Business.business_type,
            func.count(Business.id).label('count')
        ).filter(
            and_(
                Business.is_deleted == False,
                Business.is_active == False
            )
        ).group_by(Business.business_type).all()
        inactive_by_type_dict = {bt.business_type.value if hasattr(bt.business_type, "value") else bt.business_type: bt.count for bt in inactive_by_type}

        return {
            "total_businesses": total_businesses,
            "active_businesses": active_businesses,
            "inactive_businesses": total_businesses - active_businesses,
            "businesses_by_type": businesses_by_type,      # e.g., {"corporate": 10, "education": 5}
            "active_by_type": active_by_type_dict,         # e.g., {"corporate": 8, "education": 4}
            "inactive_by_type": inactive_by_type_dict      # e.g., {"corporate": 2, "education": 1}
        }

    except Exception as e:
        logger.error(f"Error getting business stats: {str(e)}")
        return {
            "total_businesses": 0,
            "active_businesses": 0,
            "inactive_businesses": 0,
            "businesses_by_type": {},
            "active_by_type": {},
            "inactive_by_type": {}
        }
    finally:
        session.close()
        ScopedSession.remove()


def get_license_stats(expiring_days: int = 30) -> Dict[str, Any]:
    """
    Get license statistics
    
    Args:
        expiring_days: Number of days to consider for "expiring soon"
        
    Returns:
        Dictionary with license statistics
    """
    session = ScopedSession()
    try:
        # Total licenses
        total_licenses = session.query(License).filter(
            License.is_deleted == False
        ).count()
        
        # Active licenses
        active_licenses = session.query(License).filter(
            and_(
                License.is_deleted == False,
                License.status == LicenseStatusEnum.ACTIVE.value
            )
        ).count()
        
        # Expired licenses
        expired_licenses = session.query(License).filter(
            and_(
                License.is_deleted == False,
                License.status == LicenseStatusEnum.EXPIRED.value
            )
        ).count()
        
        # Expiring soon
        expiry_threshold = datetime.now(timezone.utc) + timedelta(days=expiring_days)
        expiring_soon = session.query(License).filter(
            and_(
                License.is_deleted == False,
                License.status == LicenseStatusEnum.ACTIVE.value,
                License.end_date <= expiry_threshold,
                License.end_date >= datetime.now(timezone.utc)
            )
        ).count()
        
        # Licenses by tier
        license_tiers = session.query(
            License.subscription_tier,
            func.count(License.id).label('count')
        ).filter(
            License.is_deleted == False
        ).group_by(License.subscription_tier).all()
        
        licenses_by_tier = {lt.subscription_tier: lt.count for lt in license_tiers}
        
        return {
            "total_licenses": total_licenses,
            "active_licenses": active_licenses,
            "expired_licenses": expired_licenses,
            "expiring_soon_licenses": expiring_soon,
            "licenses_by_tier": licenses_by_tier
        }
        
    except Exception as e:
        logger.error(f"Error getting license stats: {str(e)}")
        return {
            "total_licenses": 0,
            "active_licenses": 0,
            "expired_licenses": 0,
            "expiring_soon_licenses": 0,
            "licenses_by_tier": {}
        }
    finally:
        session.close()
        ScopedSession.remove()


def get_each_organization_details(user_id: str, is_super_admin: bool = False) -> Dict[str, Any]:
    session = ScopedSession()
    try:
        results = []

        if is_super_admin:
            # Fetch all organizations (for super-admin)
            organizations = session.query(Organization).filter(
                Organization.is_deleted == False
            ).all()
        else:
            # Fetch only the organization of the logged-in user (admin)
            user_profile = session.query(UserProfile).filter(
                and_(
                    UserProfile.user_id == user_id,
                    UserProfile.is_active == True
                )
            ).first()

            if not user_profile or not user_profile.org_id:
                return {"message": "User does not belong to any organization", "data": {}}

            organizations = session.query(Organization).filter(
                and_(
                    Organization.id == user_profile.org_id,
                    Organization.is_deleted == False
                )
            ).all()

        # Build stats for each organization
        for org in organizations:
            business_stats = []
            for biz in org.businesses:
                total_users = session.query(Users).join(
                    UserProfile, UserProfile.user_id == Users.user_id
                ).filter(
                    and_(
                        Users.is_deleted == False,
                        UserProfile.business_id == biz.id
                    )
                ).count()

                active_users = session.query(Users).join(
                    UserProfile, UserProfile.user_id == Users.user_id
                ).filter(
                    and_(
                        Users.is_deleted == False,
                        Users.is_active == True,
                        UserProfile.business_id == biz.id
                    )
                ).count()

                business_stats.append({
                    "business_id": str(biz.id),
                    "business_name": biz.name,
                    "business_type": biz.business_type,
                    "total_users": total_users,
                    "active_users": active_users,
                    "inactive_users": total_users - active_users
                })

            results.append({
                "organization_id": str(org.id),
                "organization_name": org.name,
                "businesses": business_stats
            })

        return {"data": results}

    except Exception as e:
        logger.error(f"Error getting organization-business-user stats: {str(e)}")
        return {"message": "Error fetching stats", "data": {}}
    finally:
        session.close()
        ScopedSession.remove()


def get_document_count_by_categories() -> List[Dict[str, Any]]:
    """
    Get file counts grouped by category.

    Returns:
        List of dicts with category_id, category_name, and file_count
    """
    session = ScopedSession()
    try:
        results = (
            session.query(
                Category.id,
                Category.name,
                Category.display_name,
                func.count(File.id).label("file_count")
            )
            .outerjoin(
                File,
                and_(
                    File.category_id == Category.id,
                    File.is_deleted == False
                )
            )
            .filter(Category.is_deleted == False)
            .group_by(Category.id, Category.name, Category.display_name)
            .all()
        )

        return [
            {
                "category_id": str(cat_id),
                "category_name": cat_name,
                "file_count": file_count,
                "display_name": cat_displayname
            }
            for cat_id, cat_name, cat_displayname, file_count in results
        ]

    except Exception as e:
        logger.error(f"Error getting document counts by categories: {str(e)}")
        return []
    finally:
        session.close()
        ScopedSession.remove()

