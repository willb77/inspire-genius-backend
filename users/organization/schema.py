from typing import Optional, List, Dict, Any
import uuid
import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy.sql import func
from sqlalchemy import and_, or_
from prism_inspire.db.session import ScopedSession
from prism_inspire.core.log_config import logger
from prism_inspire.core.file_utils import S3FileHandler
from users.license.schema import get_licenses
from users.models.user import (
    Organization, OrganizationAdmin, Business,
    UserProfile, Users, UserInvitation,
    OrganizationAgent, OrganizationAgentPreferenceTone,
    BusinessAgent,
    InvitationStatusEnum, BusinessTypeEnum, OrganizationTypeEnum
)
from users.models.rbac import Roles
from ai.models.agents import Agent
from users.rbac.schema import get_role_id
from users.auth_service.utils import get_full_name

# Utility function for logo URLs
def generate_logo_url(organization: Organization, expiration: int = 3600) -> Optional[str]:
    """
    Generate presigned URL for organization logo

    Args:
        organization: Organization object
        expiration: URL expiration time in seconds (default 1 hour)

    Returns:
        Presigned URL string or None if no logo
    """
    if not organization.logo:
        return None

    try:
        file_handler = S3FileHandler(prefix="organization-logos/")
        logo_url = file_handler.generate_presigned_url(
            organization.logo,
            expiration=expiration
        )
        return logo_url
    except Exception as e:
        logger.error(f"Error generating logo URL: {str(e)}")
        return None


# Organization CRUD Operations
def create_organization(data: Dict[str, Any]) -> Optional[str]:
    """
    Create a new organization with type and auto-create business with same name

    Args:
        data: Dictionary containing organization data including 'type'

    Returns:
        Organization ID as string if successful, None otherwise
    """
    session = ScopedSession()
    try:
        # Get organization type from data
        org_type = data.get("type", OrganizationTypeEnum.BOTH)
        if isinstance(org_type, str):
            org_type = OrganizationTypeEnum(org_type)

        organization = Organization(
            id=uuid.uuid4(),
            name=data["name"],
            contact=data["contact"],
            email=data.get("email"),
            address=data.get("address"),
            website_url=data.get("website_url"),
            logo=data.get("logo"),
            type=org_type,
            is_onboarded=False,
            status=True,
            is_deleted=False
        )

        session.add(organization)
        session.flush()  # Flush to get the organization ID

        # Auto-create business(es) based on organization type
        if org_type == OrganizationTypeEnum.BOTH:
            # Create both corporate and education businesses
            corporate_business = Business(
                id=uuid.uuid4(),
                organization_id=organization.id,
                name=data["name"],
                business_type=BusinessTypeEnum.CORPORATE,
                is_onboarded=False,
                is_active=True,
                is_deleted=False
            )
            education_business = Business(
                id=uuid.uuid4(),
                organization_id=organization.id,
                name=data["name"],
                business_type=BusinessTypeEnum.EDUCATION,
                is_onboarded=False,
                is_active=True,
                is_deleted=False
            )
            session.add(corporate_business)
            session.add(education_business)
        elif org_type == OrganizationTypeEnum.CORPORATE:
            # Create only corporate business
            business = Business(
                id=uuid.uuid4(),
                organization_id=organization.id,
                name=data["name"],
                business_type=BusinessTypeEnum.CORPORATE,
                is_onboarded=False,
                is_active=True,
                is_deleted=False
            )
            session.add(business)
        elif org_type == OrganizationTypeEnum.EDUCATION:
            # Create only education business
            business = Business(
                id=uuid.uuid4(),
                organization_id=organization.id,
                name=data["name"],
                business_type=BusinessTypeEnum.EDUCATION,
                is_onboarded=False,
                is_active=True,
                is_deleted=False
            )
            session.add(business)

        session.commit()

        logger.info(f"Organization created successfully with type {org_type.value}: {organization.id}")
        return str(organization.id)

    except Exception as e:
        session.rollback()
        logger.error(f"Error creating organization: {str(e)}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def get_all_organizations(include_deleted: bool = False) -> List[Organization]:
    """
    Get all organizations
    
    Args:
        include_deleted: Whether to include deleted organizations
        
    Returns:
        List of Organization objects
    """
    session = ScopedSession()
    try:
        query = session.query(Organization)
        
        if not include_deleted:
            query = query.filter(Organization.is_deleted == False)
            
        return query.order_by(Organization.created_at.desc()).all()
        
    except Exception as e:
        logger.error(f"Error fetching organizations: {str(e)}")
        return []
    finally:
        session.close()
        ScopedSession.remove()


def get_organization_by_id(org_id: str) -> Optional[Organization]:
    """
    Get organization by ID
    
    Args:
        org_id: Organization ID
        
    Returns:
        Organization object if found, None otherwise
    """
    session = ScopedSession()
    try:
        return session.query(Organization).filter(
            and_(
                Organization.id == org_id,
                Organization.is_deleted == False
            )
        ).first()
        
    except Exception as e:
        logger.error(f"Error fetching organization {org_id}: {str(e)}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def update_organization(org_id: str, data: Dict[str, Any]) -> bool:
    """
    Update organization information (excluding type field)
    Sets is_onboarded=True if organization has an active company admin

    Args:
        org_id: Organization ID
        data: Dictionary containing updated organization data

    Returns:
        True if successful, False otherwise
    """
    session = ScopedSession()
    try:
        organization = session.query(Organization).filter(
            and_(
                Organization.id == org_id,
                Organization.is_deleted == False
            )
        ).first()

        if not organization:
            return False

        # Update fields (excluding type which should not be updated)
        if "name" in data:
            organization.name = data["name"]
        if "contact" in data:
            organization.contact = data["contact"]
        if "email" in data:
            organization.email = data["email"]
        if "address" in data:
            organization.address = data["address"]
        if "website_url" in data:
            organization.website_url = data["website_url"]
        if "logo" in data:
            organization.logo = data["logo"]

        # Check if organization has an active admin and set is_onboarded=True
        has_admin = session.query(OrganizationAdmin).filter(
            and_(
                OrganizationAdmin.organization_id == org_id,
                OrganizationAdmin.is_active == True
            )
        ).first()

        if has_admin and not organization.is_onboarded:
            organization.is_onboarded = True
            logger.info(f"Organization {org_id} marked as onboarded (has active admin)")

        organization.updated_at = datetime.now(timezone.utc)
        session.commit()

        logger.info(f"Organization updated successfully: {org_id}")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error updating organization {org_id}: {str(e)}")
        return False
    finally:
        session.close()
        ScopedSession.remove()


def deactivate_organization(org_id: str) -> bool:
    """
    Deactivate an organization (soft delete)

    Args:
        org_id: Organization ID

    Returns:
        True if successful, False otherwise
    """
    session = ScopedSession()
    try:
        organization = session.query(Organization).filter(
            Organization.id == org_id
        ).first()

        if not organization:
            return False

        organization.status = False
        organization.is_deleted = True
        organization.updated_at = datetime.now(timezone.utc)

        session.commit()

        logger.info(f"Organization deactivated: {org_id}")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error deactivating organization {org_id}: {str(e)}")
        return False
    finally:
        session.close()
        ScopedSession.remove()


def assign_agents_to_organization(
    organization_id: str,
    agent_preferences: List[Dict[str, Any]],
    assigned_by: Optional[str] = None
) -> Dict[str, List[str]]:
    """
    Assign agents to an organization with preferences (accent, tone, gender)

    Args:
        organization_id: Organization ID
        agent_preferences: List of dicts with agent_id, tone_ids, accent_id, gender_id
        assigned_by: User ID who is making the assignment

    Returns:
        Dict with success and failed agent IDs
    """
    session = ScopedSession()
    try:
        assignment_ids = []
        failed_agents = []

        for pref in agent_preferences:
            agent_id = pref.get("agent_id")
            tone_ids = pref.get("tone_ids", [])
            accent_id = pref.get("accent_id")
            gender_id = pref.get("gender_id")

            # Check if assignment already exists
            existing = session.query(OrganizationAgent).filter(
                and_(
                    OrganizationAgent.organization_id == organization_id,
                    OrganizationAgent.agent_id == agent_id,
                    OrganizationAgent.is_active == True
                )
            ).first()

            if existing:
                # Update existing assignment with new preferences
                existing.accent_id = accent_id
                existing.gender_id = gender_id

                # Delete existing tone associations
                session.query(OrganizationAgentPreferenceTone).filter_by(
                    organization_agent_id=existing.id
                ).delete()

                # Add new tone associations
                for tone_id in tone_ids:
                    tone_assoc = OrganizationAgentPreferenceTone(
                        id=uuid.uuid4(),
                        organization_agent_id=existing.id,
                        tone_id=tone_id
                    )
                    session.add(tone_assoc)

                assignment_ids.append(str(existing.id))
            else:
                # Create new assignment
                assignment = OrganizationAgent(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    agent_id=agent_id,
                    assigned_by=assigned_by,
                    is_active=True,
                    accent_id=accent_id,
                    gender_id=gender_id
                )

                session.add(assignment)
                session.flush()  # Get the ID before adding tones

                # Add tone associations
                for tone_id in tone_ids:
                    tone_assoc = OrganizationAgentPreferenceTone(
                        id=uuid.uuid4(),
                        organization_agent_id=assignment.id,
                        tone_id=tone_id
                    )
                    session.add(tone_assoc)

                assignment_ids.append(str(assignment.id))

        session.commit()

        logger.info(f"Assigned {len(assignment_ids)} agents to organization {organization_id}")
        return {
            "success": assignment_ids,
            "failed": failed_agents
        }

    except Exception as e:
        session.rollback()
        logger.error(f"Error assigning agents to organization: {str(e)}")
        return {"success": [], "failed": [p.get("agent_id") for p in agent_preferences]}
    finally:
        session.close()
        ScopedSession.remove()


def get_organization_agents(organization_id: str) -> List[OrganizationAgent]:
    """
    Get agents assigned to an organization with their preferences (accent, gender, tones)

    Args:
        organization_id: Organization ID

    Returns:
        List of OrganizationAgent objects with loaded relationships
    """
    session = ScopedSession()
    try:
        from sqlalchemy.orm import joinedload

        return session.query(OrganizationAgent).filter(
            and_(
                OrganizationAgent.organization_id == organization_id,
                OrganizationAgent.is_active == True
            )
        ).options(
            joinedload(OrganizationAgent.accent),
            joinedload(OrganizationAgent.gender),
            joinedload(OrganizationAgent.tones).joinedload(OrganizationAgentPreferenceTone.tone)
        ).all()

    except Exception as e:
        logger.error(f"Error fetching organization agents: {str(e)}")
        return []
    finally:
        session.close()
        ScopedSession.remove()


def remove_agent_from_organization(
    organization_id: str,
    agent_id: str
) -> bool:
    """
    Remove an agent from an organization (deactivate assignment)

    Args:
        organization_id: Organization ID
        agent_id: Agent ID to remove
        removed_by: User ID who is making the removal

    Returns:
        True if successful, False otherwise
    """
    session = ScopedSession()
    try:
        # Find active assignment
        assignment = session.query(OrganizationAgent).filter(
            and_(
                OrganizationAgent.organization_id == organization_id,
                OrganizationAgent.agent_id == agent_id,
            )
        ).first()

        if not assignment:
            logger.warning(f"No active assignment found for agent {agent_id} in organization {organization_id}")
            return False

        # Deactivate the assignment
        session.delete(assignment)

        session.commit()

        logger.info(f"Deleted agent {agent_id} from organization {organization_id}")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error removing agent from organization: {str(e)}")
        return False
    finally:
        session.close()
        ScopedSession.remove()

def delete_agent_from_organization(
    organization_id: str,
    agent_id: str
) -> bool:
    """
    Delete an agent assignment from a business (HTTP DELETE semantics, idempotent).

    Args:
        organization_id: Organization ID
        agent_id: Agent ID to remove

    Returns:
        True if successful or already deleted, False otherwise
    """
    session = ScopedSession()
    try:
        # Find active assignment
        assignment = session.query(OrganizationAgent).filter(
            and_(
                OrganizationAgent.organization_id == organization_id,
                OrganizationAgent.agent_id == agent_id,
            )
        ).first()

        if not assignment:
            logger.info(f"No assignment found for agent {agent_id} in organization {organization_id}")
            return True

        # Deactivate the assignment
        session.delete(assignment)

        session.commit()

        logger.info(f"Deleted agent {agent_id} from organization {organization_id}")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error removing agent from organization: {str(e)}")
        return False
    finally:
        session.close()
        ScopedSession.remove()


# ============ Business Agent Assignment Functions ============

def assign_agents_to_business(
    business_id: str,
    agent_ids: List[str]
) -> Dict[str, List[str]]:
    """
    Give business access to agents from parent organization.
    Business uses the same agent settings as organization (no separate preferences).

    Args:
        business_id: Business ID
        agent_ids: List of agent IDs to give access to

    Returns:
        Dict with success and failed agent IDs
    """
    session = ScopedSession()
    try:
        # Get business and its organization
        business = session.query(Business).filter_by(id=business_id).first()
        if not business:
            logger.error(f"Business {business_id} not found")
            return {"success": [], "failed": agent_ids}

        organization_id = business.organization_id

        # Get all active agents assigned to the organization
        org_agents = session.query(OrganizationAgent.agent_id).filter(
            and_(
                OrganizationAgent.organization_id == organization_id,
                OrganizationAgent.is_active == True
            )
        ).all()
        org_agent_ids = {str(agent.agent_id) for agent in org_agents}

        assignment_ids = []
        failed_agents = []

        for agent_id in agent_ids:
            # Validate that agent is assigned to parent organization
            if str(agent_id) not in org_agent_ids:
                logger.warning(f"Agent {agent_id} not assigned to organization {organization_id}")
                failed_agents.append(agent_id)
                continue

            # Check if assignment already exists
            existing = session.query(BusinessAgent).filter(
                and_(
                    BusinessAgent.business_id == business_id,
                    BusinessAgent.agent_id == agent_id
                )
            ).first()

            if existing:
                # Already assigned, just mark as active
                existing.is_active = True
                assignment_ids.append(str(existing.id))
            else:
                # Create new assignment (simple access, no preferences)
                assignment = BusinessAgent(
                    id=uuid.uuid4(),
                    business_id=business_id,
                    agent_id=agent_id,
                    is_active=True
                )
                session.add(assignment)
                session.flush()
                assignment_ids.append(str(assignment.id))

        session.commit()

        logger.info(f"Assigned {len(assignment_ids)} agents to business {business_id}")
        return {
            "success": assignment_ids,
            "failed": failed_agents
        }

    except Exception as e:
        session.rollback()
        logger.error(f"Error assigning agents to business: {str(e)}")
        return {"success": [], "failed": agent_ids}
    finally:
        session.close()
        ScopedSession.remove()


def get_business_agents_with_org_settings(business_id: str) -> List[Dict[str, Any]]:
    """
    Get agents assigned to a business with organization settings.
    Business inherits all agent settings from the parent organization.

    Args:
        business_id: Business ID

    Returns:
        List of dicts with business agent and organization settings
    """
    session = ScopedSession()
    try:
        from sqlalchemy.orm import joinedload
        # Get business and its organization
        business = session.query(Business).filter_by(id=business_id).first()
        if not business:
            return []

        organization_id = business.organization_id

        # Get business agents with their organization settings
        business_agents = session.query(BusinessAgent).filter(
            BusinessAgent.business_id == business_id
        ).all()

        result = []
        for ba in business_agents:
            # Get organization agent settings for this agent
            org_agent = session.query(OrganizationAgent).filter(
                and_(
                    OrganizationAgent.organization_id == organization_id,
                    OrganizationAgent.agent_id == ba.agent_id
                )
            ).options(
                # Eager load preference tones
                joinedload(OrganizationAgent.accent),
                joinedload(OrganizationAgent.gender),
                joinedload(OrganizationAgent.tones),
                joinedload(OrganizationAgent.tones).joinedload(OrganizationAgentPreferenceTone.tone)
            ).first()

            if org_agent:
                result.append({
                    "business_assignment_id": ba.id,
                    "agent_id": ba.agent_id,
                    "is_active": ba.is_active,
                    "created_at": ba.created_at,
                    "org_agent": org_agent  # Contains all organization settings
                })

        return result

    except Exception as e:
        logger.error(f"Error fetching business agents with org settings: {str(e)}")
        return []
    finally:
        session.close()
        ScopedSession.remove()


def remove_agent_from_business(
    business_id: str,
    agent_id: str
) -> bool:
    """
    Remove an agent from a business (delete assignment)

    Args:
        business_id: Business ID
        agent_id: Agent ID to remove

    Returns:
        True if successful, False otherwise
    """
    session = ScopedSession()
    try:
        assignment = session.query(BusinessAgent).filter(
            and_(
                BusinessAgent.business_id == business_id,
                BusinessAgent.agent_id == agent_id
            )
        ).first()

        if not assignment:
            logger.warning(f"No assignment found for agent {agent_id} in business {business_id}")
            return False

        session.delete(assignment)
        session.commit()

        logger.info(f"Deleted agent {agent_id} from business {business_id}")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error removing agent from business: {str(e)}")
        return False
    finally:
        session.close()
        ScopedSession.remove()


def get_all_organizations(page: int = 1, limit: int = 10) -> Dict[str, Any]:
    """
    Get all organizations with pagination

    Args:
        page: Page number
        limit: Items per page

    Returns:
        Dictionary with organizations list and pagination info
    """
    session = ScopedSession()
    try:
        # Base query
        query = session.query(Organization).filter(Organization.is_deleted == False)

        # Get total count
        total = query.count()

        # Apply pagination
        query = query.order_by(Organization.created_at.desc())
        offset = (page - 1) * limit
        organizations = query.offset(offset).limit(limit).all()

        return {
            "organizations": organizations,
            "total": total,
            "page": page,
            "limit": limit
        }

    except Exception as e:
        logger.error(f"Error fetching organizations: {str(e)}")
        return {"organizations": [], "total": 0, "page": page, "limit": limit}
    finally:
        session.close()
        ScopedSession.remove()


# Business CRUD Operations
def create_business(data: Dict[str, Any]) -> Optional[str]:
    """
    Create a new business within an organization
    
    Args:
        data: Dictionary containing business data
        
    Returns:
        Business ID as string if successful, None otherwise
    """
    session = ScopedSession()
    try:
        # Check business limit (max 2 per organization)
        existing_count = session.query(Business).filter(
            Business.organization_id == data["organization_id"],
            Business.is_deleted == False
        ).count()
        
        if existing_count >= 2:
            logger.warning(f"Organization {data['organization_id']} already has maximum businesses")
            return None
        
        business = Business(
            id=uuid.uuid4(),
            organization_id=data["organization_id"],
            name=data["name"],
            description=data.get("description"),
            contact_email=data.get("contact_email"),
            contact_phone=data.get("contact_phone"),
            business_type=BusinessTypeEnum(data.get("business_type", "corporate")),
            is_active=True,
            is_deleted=False
        )
        
        session.add(business)
        session.commit()
        
        logger.info(f"Business created successfully: {business.id}")
        return str(business.id)
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error creating business: {str(e)}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def update_business(business_id: str, data: Dict[str, Any]) -> bool:
    """
    Update existing business name only
    Sets is_onboarded=True after successful update

    Args:
        business_id: Business ID
        data: Dictionary containing updated business name

    Returns:
        True if successful, False otherwise
    """
    session = ScopedSession()
    try:
        business = session.query(Business).filter(
            Business.id == business_id,
            Business.is_deleted == False
        ).first()

        if not business:
            return False

        # Only update name field (as per requirements)
        if "name" in data:
            business.name = data["name"]

        # Set is_onboarded to True after successful update (if it was False)
        if not business.is_onboarded:
            business.is_onboarded = True
            logger.info(f"Business {business_id} marked as onboarded after update")

        business.updated_at = datetime.now(timezone.utc)
        session.commit()

        logger.info(f"Business updated successfully: {business_id}")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error updating business {business_id}: {str(e)}")
        return False
    finally:
        session.close()
        ScopedSession.remove()


def deactivate_business(business_id: str) -> bool:
    """
    Deactivate/delete a business (soft delete)
    
    Args:
        business_id: Business ID
        
    Returns:
        True if successful, False otherwise
    """
    session = ScopedSession()
    try:
        business = session.query(Business).filter(
            Business.id == business_id,
            Business.is_deleted == False
        ).first()
        
        if not business:
            return False
        
        business.is_active = False
        business.is_deleted = True
        business.updated_at = datetime.now(timezone.utc)
        
        session.commit()
        
        logger.info(f"Business deactivated: {business_id}")
        return True
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error deactivating business {business_id}: {str(e)}")
        return False
    finally:
        session.close()
        ScopedSession.remove()


def get_organization_businesses(org_id: str) -> List[Business]:
    """
    Get all businesses for an organization

    Args:
        org_id: Organization ID

    Returns:
        List of Business objects
    """
    session = ScopedSession()
    try:
        businesses = session.query(Business).filter(
            Business.organization_id == org_id,
            Business.is_deleted == False
        ).order_by(Business.created_at.desc()).all()

        return businesses

    except Exception as e:
        logger.error(f"Error getting businesses for organization {org_id}: {str(e)}")
        return []
    finally:
        session.close()
        ScopedSession.remove()


def check_organization_has_admin(org_id: str) -> bool:
    """
    Check if an organization already has an active admin
    Organization admin has org_id, business_id IS NULL, and role=admin

    Args:
        org_id: Organization ID

    Returns:
        True if organization has an active admin, False otherwise
    """
    session = ScopedSession()
    try:
        admin_role_id = get_role_id("admin", create_if_missing=True)

        if not admin_role_id:
            return False

        admin_exists = session.query(UserProfile).join(
            Users, UserProfile.user_id == Users.user_id
        ).filter(
            UserProfile.org_id == org_id,
            UserProfile.business_id.is_(None),
            UserProfile.role == admin_role_id,
            Users.is_deleted == False
        ).first()

        return admin_exists is not None

    except Exception as e:
        logger.error(f"Error checking organization admin: {str(e)}")
        return False
    finally:
        session.close()
        ScopedSession.remove()


def check_business_has_admin(organization_id: str, business_id: str) -> bool:
    """
    Check if a business already has an active admin
    Business admin must have both organization_id and business_id

    Args:
        organization_id: Organization ID
        business_id: Business ID

    Returns:
        True if business has an active admin, False otherwise
    """
    session = ScopedSession()
    try:
        admin_role_id = get_role_id("admin", create_if_missing=True)

        if not admin_role_id:
            return False

        admin_exists = session.query(UserProfile).join(
            Users, UserProfile.user_id == Users.user_id
        ).filter(
            and_(
                UserProfile.org_id == organization_id,
                UserProfile.business_id == business_id,
                UserProfile.role == admin_role_id,
                Users.is_active == True,
                Users.is_deleted == False
            )
        ).first()

        return admin_exists is not None

    except Exception as e:
        logger.error(f"Error checking business admin: {str(e)}")
        return False
    finally:
        session.close()
        ScopedSession.remove()


def create_organization_admin(org_id: str, user_id: str, assigned_by: Optional[str] = None) -> Optional[str]:
    """
    Create an organization admin record

    Args:
        org_id: Organization ID
        user_id: User ID to assign as admin
        assigned_by: User ID who is making the assignment

    Returns:
        OrganizationAdmin ID if successful, None otherwise
    """
    session = ScopedSession()
    try:
        # Check if this user is already an admin of this organization
        existing = session.query(OrganizationAdmin).filter(
            and_(
                OrganizationAdmin.organization_id == org_id,
                OrganizationAdmin.user_id == user_id,
                OrganizationAdmin.is_active == True
            )
        ).first()

        if existing:
            logger.info(f"User {user_id} is already an admin of organization {org_id}")
            return str(existing.id)

        organization_admin = OrganizationAdmin(
            id=uuid.uuid4(),
            organization_id=org_id,
            user_id=user_id,
            assigned_by=assigned_by,
            is_active=True
        )

        session.add(organization_admin)
        session.commit()

        logger.info(f"Organization admin created: {organization_admin.id}")
        return str(organization_admin.id)

    except Exception as e:
        session.rollback()
        logger.error(f"Error creating organization admin: {str(e)}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def get_organization_admin(org_id: str, business_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get the active admin for an organization or business

    Args:
        org_id: Organization ID
        business_id: Business ID (optional). If provided, returns business admin instead of org admin

    Returns:
        Dictionary with admin details (user_id, admin_name, admin_email, admin_is_active) or None
    """
    session = ScopedSession()
    try:
        admin_role_id = get_role_id("admin", create_if_missing=True)

        if not admin_role_id:
            return None

        # Build filter conditions
        if business_id:
            # Business admin: has org_id AND business_id AND role=admin
            profile = session.query(UserProfile).join(
                Users, UserProfile.user_id == Users.user_id
            ).filter(
                UserProfile.org_id == org_id,
                UserProfile.business_id == business_id,
                UserProfile.role == admin_role_id,
                Users.is_deleted == False
            ).first()
        else:
            # Organization admin: has org_id AND business_id IS NULL AND role=admin
            profile = session.query(UserProfile).join(
                Users, UserProfile.user_id == Users.user_id
            ).filter(
                UserProfile.org_id == org_id,
                UserProfile.business_id.is_(None),
                UserProfile.role == admin_role_id,
                Users.is_deleted == False
            ).first()

        if not profile:
            return None

        # Get user details
        user = session.query(Users).filter(
            Users.user_id == profile.user_id
        ).first()

        if not user:
            return None

        # Build admin name from profile
        admin_name = get_full_name(profile.first_name, profile.last_name)

        return {
            "user_id": str(profile.user_id),
            "admin_name": admin_name,
            "admin_email": user.email,
            "admin_is_active": user.is_active
        }

    except Exception as e:
        logger.error(f"Error getting organization admin: {str(e)}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def get_business_with_admin_info(org_id: str, business: Business) -> Dict[str, Any]:
    """
    Helper function to build business data with admin information

    Args:
        org_id: Organization ID
        business: Business object

    Returns:
        Dictionary with business details including admin info
    """
    # Get business admin info
    business_admin_info = get_organization_admin(org_id, str(business.id))

    return {
        "id": str(business.id),
        "name": business.name,
        "description": business.description,
        "contact_email": business.contact_email,
        "contact_phone": business.contact_phone,
        "business_type": business.business_type.value,
        "is_onboarded": business.is_onboarded if hasattr(business, 'is_onboarded') else False,
        "is_active": business.is_active,
        "created_at": business.created_at.isoformat() if business.created_at else None,
        "admin_name": business_admin_info.get("admin_name") if business_admin_info else None,
        "admin_email": business_admin_info.get("admin_email") if business_admin_info else None,
        "admin_is_active": business_admin_info.get("admin_is_active") if business_admin_info else None
    }


def get_organization_details_for_response(org_id: str, include_full_details: bool = False) -> Optional[Dict[str, Any]]:
    """
    Helper function to get organization details for API responses

    Args:
        org_id: Organization ID
        include_full_details: If True, includes businesses, license, and coach details

    Returns:
        Dictionary with organization details or None
    """
    session = ScopedSession()
    try:
        organization = get_organization_by_id(org_id)
        if not organization:
            return None

        # Get admin info
        admin_info = get_organization_admin(org_id)

        # Base organization data
        org_data = {
            "id": str(organization.id),
            "name": organization.name,
            "type": organization.type.value if hasattr(organization, 'type') and organization.type else None,
            "status": organization.status,
            "admin_name": admin_info.get("admin_name") if admin_info else None,
            "admin_email": admin_info.get("admin_email") if admin_info else None,
            "admin_is_active": admin_info.get("admin_is_active") if admin_info else None,
            "created_at": organization.created_at.isoformat() if organization.created_at else None,
        }

        # Add full details if requested
        if include_full_details:
            # Get businesses with admin info
            businesses = get_organization_businesses(org_id)
            business_list = [
                get_business_with_admin_info(org_id, business)
                for business in businesses
            ]

            # Get license info (support multiple licenses)
            licenses = get_licenses(org_id)
            license_data = None
            licenses_list = []
            if licenses:
                for lic in licenses:
                    try:
                        # prefer model property days_until_expiry which handles tz and logic
                        days_remaining = lic.days_until_expiry if hasattr(lic, 'days_until_expiry') else None
                    except Exception:
                        days_remaining = None

                    licenses_list.append({
                        "id": str(lic.id) if hasattr(lic, 'id') else None,
                        "subscription_tier": getattr(lic, 'subscription_tier', None),
                        "status": getattr(lic, 'status', None),
                        "start_date": lic.start_date.isoformat() if getattr(lic, 'start_date', None) else None,
                        "end_date": lic.end_date.isoformat() if getattr(lic, 'end_date', None) else None,
                        "days_remaining": days_remaining,
                        "is_active": getattr(lic, 'is_active', None)
                    })

            # Get agent/coach info (support multiple assigned agents)
            from ai.models.agents import Agent
            agents = get_organization_agents(org_id)
            coach_name = None
            agent_data = None
            coaches_list = []

            for a in agents:
                try:
                    agent_record = session.query(Agent).filter(Agent.id == a.agent_id).first()
                    coach_name = agent_record.name if agent_record else None

                    # Get agent-specific voice preferences from the OrganizationAgent record
                    agent_preferences = {
                        "gender": a.gender.name if a.gender else None,
                        "accent": a.accent.name if a.accent else None,
                        "tones": [tone_assoc.tone.name for tone_assoc in a.tones] if a.tones else []
                    }

                    coaches_list.append({
                        "id": str(a.agent_id),
                        "name": coach_name,
                        "organization_id": str(a.organization_id) if getattr(a, 'organization_id', None) else None,
                        "assigned_by": str(a.assigned_by) if getattr(a, 'assigned_by', None) else None,
                        "is_active": getattr(a, 'is_active', None),
                        "traits": agent_preferences,
                        "created_at": a.created_at.isoformat() if getattr(a, 'created_at', None) else None,
                        "updated_at": a.updated_at.isoformat() if getattr(a, 'updated_at', None) else None
                    })
                except Exception:
                    # Skip problematic agent but continue
                    continue

            # Add full details to org_data
            org_data.update({
                "contact": organization.contact,
                "email": organization.email,
                "address": organization.address,
                "website_url": organization.website_url,
                "is_onboarded": organization.is_onboarded if hasattr(organization, 'is_onboarded') else False,
                "logo": organization.logo,
                "logo_url": generate_logo_url(organization),
                "created_at": organization.created_at.isoformat() if organization.created_at else None,
                "updated_at": organization.updated_at.isoformat() if organization.updated_at else None,
                "businesses": business_list,
                "licenses": licenses_list,
                "coaches": coaches_list
            })

        return org_data

    except Exception as e:
        logger.error(f"Error getting organization details: {str(e)}")
        return None
    finally:
        session.close()
        ScopedSession.remove()
