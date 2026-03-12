import uuid
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from ai.models.agents import Accent, Agent, Category, Gender, Prompt, Tone, UserPreference, UserPreferenceTone, UserAgentAssignment
from users.models.user import OrganizationAgent, OrganizationAgentPreferenceTone, BusinessAgent, UserProfile
from ai.models.files import File
from prism_inspire.core.log_config import logger
from prism_inspire.db.session import ScopedSession
from users.auth_service.utils import get_full_name


def set_user_agent_preference(user_id, agent_id, tone_ids, accent_id, gender_id, on_login=False) -> Optional[uuid.UUID]:
    """
    Set or update user agent preferences with support for multiple tones and gender

    Args:
        user_id: User's UUID
        agent_id: Agent's UUID
        tone_ids: List of Tone UUIDs (supports multiple selections)
        accent_id: Accent UUID
        gender_id: Gender UUID
        on_login: If True, skip update if preference exists

    Returns:
        Preference ID if successful, None otherwise
    """
    try:
        session = ScopedSession()
        existing = (
            session.query(UserPreference)
            .filter_by(user_id=user_id, agent_id=agent_id)
            .first()
        )

        if existing:
            if on_login:
                return existing.id

            # Update accent and gender
            existing.accent_id = accent_id
            existing.gender_id = gender_id

            # Delete existing tone associations
            session.query(UserPreferenceTone).filter_by(
                user_preference_id=existing.id
            ).delete()

            # Add new tone associations
            if tone_ids:
                for tone_id in tone_ids:
                    tone_assoc = UserPreferenceTone(
                        id=uuid.uuid4(),
                        user_preference_id=existing.id,
                        tone_id=tone_id
                    )
                    session.add(tone_assoc)

            pref_id = existing.id
        else:
            # Create new preference
            new_pref = UserPreference(
                id=uuid.uuid4(),
                user_id=user_id,
                agent_id=agent_id,
                accent_id=accent_id,
                gender_id=gender_id,
            )
            session.add(new_pref)
            session.flush()  # Get the ID before adding tones

            # Add tone associations
            if tone_ids:
                for tone_id in tone_ids:
                    tone_assoc = UserPreferenceTone(
                        id=uuid.uuid4(),
                        user_preference_id=new_pref.id,
                        tone_id=tone_id
                    )
                    session.add(tone_assoc)

            pref_id = new_pref.id

        session.commit()
        return pref_id
    except Exception as e:
        session.rollback()
        logger.error(f"Error setting preference: {e}")
    finally:
        session.close()
        ScopedSession.remove()
    return None


class PreferenceDataBuilder:
    """Class for building preference data dictionaries with reduced cognitive complexity."""

    @staticmethod
    def _format_datetime(dt):
        """Format datetime to ISO string."""
        return dt.isoformat() if dt else None

    @classmethod
    def _build_agent_data(cls, agent):
        """Build agent data dictionary."""
        return {
            "id": str(agent.id),
            "name": agent.name,
            "category_id": str(agent.category_id) if agent.category_id else None,
            "created_at": cls._format_datetime(agent.created_at),
        }

    @classmethod
    def _build_tone_data(cls, tone):
        """Build tone data dictionary."""
        return {
            "id": str(tone.id),
            "name": tone.name,
            "created_at": cls._format_datetime(tone.created_at),
        }

    @classmethod
    def _build_accent_data(cls, accent):
        """Build accent data dictionary."""
        return {
            "id": str(accent.id),
            "name": accent.name,
            "created_at": cls._format_datetime(accent.created_at),
        }

    @classmethod
    def _build_gender_data(cls, gender):
        """Build gender data dictionary."""
        return {
            "id": str(gender.id),
            "name": gender.name,
            "created_at": cls._format_datetime(gender.created_at),
        }

    @classmethod
    def build_preference_data(cls, preference):
        """Build complete preference data dictionary with support for multiple tones."""
        # Build tones list from many-to-many relationship
        tones_list = []
        if preference.tones:
            for tone_assoc in preference.tones:
                if tone_assoc.tone:
                    tones_list.append(cls._build_tone_data(tone_assoc.tone))

        return {
            "id": str(preference.id),
            "agent": (
                cls._build_agent_data(preference.agent) if preference.agent else None
            ),
            "tones": tones_list,  # Changed from single tone to list of tones
            "accent": (
                cls._build_accent_data(preference.accent) if preference.accent else None
            ),
            "gender": (
                cls._build_gender_data(preference.gender) if preference.gender else None
            ),
            "created_at": cls._format_datetime(preference.created_at),
        }


def get_preferences_by_user(user_id, agent_id=None):
    try:
        session = ScopedSession()
        query = session.query(UserPreference).filter_by(user_id=user_id)

        if agent_id:
            query = query.filter(UserPreference.agent_id == agent_id)

        prefs = query.all()
        result = [PreferenceDataBuilder.build_preference_data(p) for p in prefs]
        return result
    finally:
        session.close()
        ScopedSession.remove()

def get_preference_names_by_ids(accent_id, tone_ids: list, gender_id):
    """
    Get preference names (text only) by their IDs.
    
    Args:
        accent_id: UUID of the accent
        tone_ids: List of tone UUIDs
        gender_id: UUID of the gender
    
    Returns:
        Dictionary with accent_name, tone_names (list), and gender_name
    """
    try:
        session = ScopedSession()
        
        # Get accent name
        accent_name = None
        if accent_id:
            accent = session.query(Accent).filter_by(id=accent_id).first()
            accent_name = accent.name if accent else None
        
        # Get tone names
        tone_names = []
        if tone_ids:
            tones = session.query(Tone).filter(Tone.id.in_(tone_ids)).all()
            tone_names = [tone.name for tone in tones]
        
        # Get gender name
        gender_name = None
        if gender_id:
            gender = session.query(Gender).filter_by(id=gender_id).first()
            gender_name = gender.name if gender else None
        
        return {
            "accent": accent_name,
            "tones": tone_names,
            "gender": gender_name
        }
    finally:
        session.close()
        ScopedSession.remove()


def get_all_agents(
    status: str = None,
    search: str = None,
    agent_type: str = None,
    page: int = 1,
    page_size: int = 10,
    user_role: str = None,
    user_id: str = None,
):
    """
    Get agents based on user's organization/business hierarchy and custom assignments.

    Priority order:
    1. If user has business_id: Show business agents (with org preferences)
    2. Else if user has org_id: Show organization agents (with org preferences)
    3. Else: Show all predefined agents
    4. Apply user-specific custom assignments (add custom agents, remove predefined)

    Args:
        status: Filter by agent status (active/deactivated)
        search: Search by agent or category name
        agent_type: Filter by agent type (predefined/custom)
        page: Page number
        page_size: Number of items per page
        user_role: User's role (super-admin sees all)
        user_id: User's UUID for getting org/business context

    Returns:
        Tuple of (agents list, total count)
    """
    session = ScopedSession()
    try:
        # Get user's organization and business context
        org_id = None
        business_id = None
        if user_id:
            user_profile = session.query(UserProfile).filter_by(user_id=user_id).first()
            if user_profile:
                org_id = user_profile.org_id
                business_id = user_profile.business_id

        # Get user's custom assignments (assigned custom agents and removed predefined agents)
        user_assignments = get_user_assigned_agents(user_id) if user_id else {"assigned_agent_ids": [], "removed_agent_ids": []}
        assigned_custom_ids = user_assignments["assigned_agent_ids"]
        removed_predefined_ids = user_assignments["removed_agent_ids"]

        # Determine which agents to show based on hierarchy
        allowed_agent_ids = None  # None means all agents allowed

        if business_id:
            # User has business: show business agents
            business_agent_ids = get_business_agents(business_id)
            if business_agent_ids:
                allowed_agent_ids = business_agent_ids
        elif org_id:
            # User has org only: show org agents
            org_agents = get_organization_agents_with_preferences(org_id)
            if org_agents:
                allowed_agent_ids = [agent["agent_id"] for agent in org_agents]

        # Build base query
        query = session.query(Agent).options(
            joinedload(Agent.category), joinedload(Agent.prompts)
        )

        # Apply agent filtering based on hierarchy and user assignments
        if allowed_agent_ids is not None:
            # User has org/business: filter to those agents + custom assigned agents
            combined_ids = list(set(allowed_agent_ids + assigned_custom_ids))
            query = query.filter(Agent.id.in_(combined_ids))
        elif user_role != "super-admin":
            # No org/business: show predefined agents + custom assigned agents
            if assigned_custom_ids:
                query = query.filter(
                    or_(
                        Agent.type == "predefined",
                        Agent.id.in_(assigned_custom_ids)
                    )
                )
            else:
                query = query.filter(Agent.type == "predefined")
        # super-admin sees all agents without filtering

        # Remove explicitly removed agents (from custom assignments)
        if removed_predefined_ids:
            query = query.filter(~Agent.id.in_(removed_predefined_ids))

        # Filter by status
        if status:
            if status.lower() == "active":
                query = query.filter(Agent.is_active.is_(True))
            elif status.lower() == "deactivated":
                query = query.filter(Agent.is_active.is_(False))

        # Filter by type
        if agent_type:
            query = query.filter(func.lower(Agent.type) == agent_type.lower())

        # Search by name or category
        if search:
            search_term = f"%{search.lower()}%"
            query = query.join(Category, isouter=True).filter(
                or_(
                    func.lower(Agent.name).like(search_term),
                    func.lower(Category.name).like(search_term),
                )
            )

        total = query.count()
        agents = query.offset((page - 1) * page_size).limit(page_size).all()

        return agents, total, org_id, business_id
    finally:
        session.close()
        ScopedSession.remove()


def get_predefined_agents_for_toon(exclude_agent_id: str = None):
    """
    Get predefined agents in a minimal format suitable for TOON encoding.
    
    Args:
        exclude_agent_id: Agent ID to exclude (e.g., self)
    
    Returns:
        List of dicts with agent_id, agent_name, and information (prompt text)
    """
    session = ScopedSession()
    try:
        query = session.query(Agent).options(
            joinedload(Agent.prompts)
        ).filter(
            Agent.type == "predefined",
            Agent.is_active.is_(True)
        )
        
        if exclude_agent_id:
            query = query.filter(Agent.id != exclude_agent_id)
        
        agents = query.all()
        
        result = []
        for agent in agents:
            # Get the first prompt as "information"
            information = ""
            if agent.prompts and len(agent.prompts) > 0:
                information = agent.prompts[0].prompt
            
            result.append({
                "agent_id": str(agent.id),
                "agent_name": agent.name,
                "information": information
            })
        
        return result
    except Exception as e:
        logger.error(f"Error getting predefined agents for TOON: {e}")
        return []
    finally:
        session.close()
        ScopedSession.remove()

def get_all_tone():
    session = ScopedSession()
    try:
        return session.query(Tone).all()
    finally:
        session.close()
        ScopedSession.remove()


def get_all_accent():
    session = ScopedSession()
    try:
        return session.query(Accent).all()
    finally:
        session.close()
        ScopedSession.remove()


def get_all_gender():
    session = ScopedSession()
    try:
        return session.query(Gender).all()
    finally:
        session.close()
        ScopedSession.remove()


def get_org_agent_voice_details(org_id: str):
    
    session = ScopedSession()
    try:
        org_agent = (
            session.query(OrganizationAgent)
            .filter_by(organization_id=org_id).first()
        )
        
        if not org_agent:
            return {"gender": None, "accent": None, "tones": []}

        accent_name = (
            session.query(Accent.name)
            .filter(Accent.id == org_agent.accent_id)
            .scalar() if org_agent.accent_id else None
        )

        gender_name = (
            session.query(Gender.name)
            .filter(Gender.id == org_agent.gender_id)
            .scalar() if org_agent.gender_id else None
        )

        tone_names = (
            session.query(Tone.name)
            .join(OrganizationAgentPreferenceTone)
            .filter(OrganizationAgentPreferenceTone.organization_agent_id == org_agent.id)
            .all()
        )

        tone_names = [name[0] for name in tone_names]
        
        return {
            "gender": gender_name,
            "accent": accent_name,
            "tones": tone_names
        }
    finally:
        session.close()
        ScopedSession.remove()


def get_all_category():
    session = ScopedSession()
    try:
        return session.query(Category).all()
    finally:
        session.close()
        ScopedSession.remove()


def get_category_by_id(category_id):
    session = ScopedSession()
    try:
        return session.query(Category).filter_by(id=category_id).first()
    finally:
        session.close()
        ScopedSession.remove()


def get_agent_by_id(agent_id: str) -> Optional[Agent]:
    """
    Get agent by ID

    Args:
        agent_id: UUID of the agent to retrieve

    Returns:
        Agent object if found, None otherwise
    """
    session = ScopedSession()
    try:
        return session.query(Agent).filter_by(id=agent_id).first()
    except Exception as e:
        logger.error(f"Error getting agent by ID {agent_id}: {e}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def get_prompts_by_agent_id(agent_id):
    """
    Get all prompts for a specific agent

    Args:
        agent_id: UUID of the agent whose prompts to retrieve

    Returns:
        List of Prompt objects for the given agent
    """
    session = ScopedSession()
    try:
        return session.query(Prompt).filter_by(agent_id=agent_id).all()
    except Exception as e:
        logger.error(f"Error getting prompts for agent ID {agent_id}: {e}")
        return []
    finally:
        session.close()
        ScopedSession.remove()


def normalize_name(name: str) -> str:
    """Lowercase and remove spaces for consistent duplicate checks."""
    return "".join(name.lower().split())


def get_or_create_category(session, category_name: str):
    """Find category by name (case-insensitive), create if not exists."""
    category = (
        session.query(Category)
        .filter(func.lower(Category.name) == category_name.lower())
        .first()
    )
    if not category:
        category = Category(
            id=uuid.uuid4(),
            name=category_name,
            display_name=category_name,
            type="agent",
        )
        session.add(category)
        session.flush()
    return category


def create_agent(agent_data: dict):
    """Insert agent & prompt in DB and return result dict."""
    session = ScopedSession()
    try:
        # Get or create category
        category = get_or_create_category(session, agent_data["category_name"])

        # Check for duplicate name in same category
        existing_agent = (
            session.query(Agent)
            .filter(
                Agent.category_id == category.id,
                func.replace(func.lower(Agent.name), " ", "")
                == normalize_name(agent_data["name"]),
            )
            .first()
        )
        if existing_agent:
            return {
                "status": False,
                "message": f"Agent '{agent_data['name']}' already exists.",
            }

        # Create agent
        agent = Agent(
            id=uuid.uuid4(),
            name=agent_data["name"],
            category_id=category.id,
            type="custom",
        )
        session.add(agent)
        session.flush()

        # Create prompt
        prompt = Prompt(id=uuid.uuid4(), prompt=agent_data["prompt"], agent_id=agent.id)
        session.add(prompt)
        session.commit()
        logger.info(f"Agent is created succesfully. {str(agent.id)}")
        return {
            "status": True,
            "message": "Agent created successfully",
            "agent_id": str(agent.id),
            "category_id": str(category.id),
            "prompt_id": str(prompt.id),
        }

    except Exception as e:
        session.rollback()
        return {"status": False, "message": str(e)}
    finally:
        session.close()
        ScopedSession.remove()


def update_agent(agent_data: dict):
    """Update agent's name, category, or prompt."""
    session = ScopedSession()
    try:
        agent_id = agent_data.get("id")
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            return {"status": False, "message": "Agent not found"}

        # Update name
        if agent_data.get("name"):
            agent.name = agent_data["name"]

        # Update category if given
        if agent_data.get("category_name"):
            category = get_or_create_category(session, agent_data["category_name"])
            agent.category_id = category.id
        else:
            category = (
                session.query(Category).filter(Category.id == agent.category_id).first()
            )

        # Update prompt if given
        if agent_data.get("prompt") is not None:
            prompt_obj = (
                session.query(Prompt).filter(Prompt.agent_id == agent_id).first()
            )
            if prompt_obj:
                prompt_obj.prompt = agent_data["prompt"]
            else:
                prompt_obj = Prompt(
                    id=uuid.uuid4(), prompt=agent_data["prompt"], agent_id=agent.id
                )
                session.add(prompt_obj)

        if agent_data.get("status") is not None:
            if agent_data["status"].lower() == "active":
                agent.is_active = True
            elif agent_data["status"].lower() == "deactivated":
                agent.is_active = False
            else:
                return {
                    "status": False,
                    "message": "Invalid status value. Use 'active' or 'deactivated'.",
                }

        session.commit()
        logger.info(f"Agent updated successfully. {str(agent.id)}")
        return {
            "status": True,
            "message": "Agent updated successfully",
            "agent_id": str(agent.id),
            "category_id": str(category.id),
            "prompt_id": str(prompt_obj.id) if agent_data.get("prompt") else None,
        }

    except Exception as e:
        session.rollback()
        return {"status": False, "message": str(e)}
    finally:
        session.close()
        ScopedSession.remove()


def create_category(category_data: dict):
    session = ScopedSession()
    try:
        category = Category(
            id=uuid.uuid4(),
            name=category_data["name"],
            display_name=category_data.get("display_name"),
            type=category_data.get("type", "both"),
        )
        session.add(category)
        session.commit()
        return {
            "status": True,
            "message": "Category created successfully",
            "category_id": str(category.id),
        }
    except Exception as e:
        session.rollback()
        return {"status": False, "message": str(e)}
    finally:
        session.close()
        ScopedSession.remove()


def deactivate_agent(agent_id):
    session = ScopedSession()
    try:
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            return {"status": False, "message": "Agent not found"}
        if not agent.is_active:
            return {"status": False, "message": "Agent is already inactive"}

        agent.is_active = False
        session.commit()
        return {
            "status": True,
            "message": "Agent deactivated successfully",
            "agent_id": str(agent.id),
        }
    except Exception as e:
        session.rollback()
        return {"status": False, "message": str(e)}
    finally:
        session.close()
        ScopedSession.remove()


def assign_agents_to_user(user_id: str, agent_ids: list, is_active: bool = True):
    """
    Assign or remove agents for a specific user.

    Args:
        user_id: UUID of the user
        agent_ids: List of agent UUIDs to assign/remove
        is_active: True to assign agents, False to remove/block predefined agents

    Returns:
        Dictionary with status and message
    """
    session = ScopedSession()
    try:
        # Verify user exists
        user_profile = session.query(UserProfile).filter_by(user_id=user_id).first()
        if not user_profile:
            return {"status": False, "message": "User not found"}

        # Verify all agents exist
        agents = session.query(Agent).filter(Agent.id.in_(agent_ids)).all()
        if len(agents) != len(agent_ids):
            return {"status": False, "message": "One or more agents not found"}

        assignment_ids = []
        for agent_id in agent_ids:
            # Check if assignment already exists
            existing = session.query(UserAgentAssignment).filter_by(
                user_id=user_id,
                agent_id=agent_id
            ).first()

            if existing:
                # Update existing assignment
                existing.is_active = is_active
                existing.updated_at = func.now()
                assignment_ids.append(str(existing.id))
            else:
                # Create new assignment
                assignment = UserAgentAssignment(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    agent_id=agent_id,
                    is_active=is_active
                )
                session.add(assignment)
                session.flush()
                assignment_ids.append(str(assignment.id))

        session.commit()
        action = "assigned" if is_active else "removed"
        return {
            "status": True,
            "message": f"Agents {action} successfully",
            "assignment_ids": assignment_ids
        }
    except Exception as e:
        session.rollback()
        logger.error(f"Error assigning agents to user: {e}")
        return {"status": False, "message": str(e)}
    finally:
        session.close()
        ScopedSession.remove()


def get_user_assigned_agents(user_id: str):
    """
    Get all agent assignments for a user (both active and inactive)

    Args:
        user_id: UUID of the user

    Returns:
        Dictionary with assigned and removed agent IDs
    """
    session = ScopedSession()
    try:
        assignments = session.query(UserAgentAssignment).filter_by(user_id=user_id).all()

        assigned = [str(a.agent_id) for a in assignments if a.is_active]
        removed = [str(a.agent_id) for a in assignments if not a.is_active]

        return {
            "assigned_agent_ids": assigned,  # Custom agents explicitly assigned
            "removed_agent_ids": removed      # Predefined agents explicitly removed
        }
    except Exception as e:
        logger.error(f"Error getting user assigned agents: {e}")
        return {
            "assigned_agent_ids": [],
            "removed_agent_ids": []
        }
    finally:
        session.close()
        ScopedSession.remove()


def get_organization_agents_with_preferences(org_id: str):
    """
    Get all agents assigned to an organization with their accent, tone, gender preferences

    Args:
        org_id: UUID of the organization

    Returns:
        List of agent dictionaries with preferences
    """
    session = ScopedSession()
    try:
        org_agents = (
            session.query(OrganizationAgent)
            .options(
                joinedload(OrganizationAgent.accent),
                joinedload(OrganizationAgent.gender),
                joinedload(OrganizationAgent.tones).joinedload(OrganizationAgentPreferenceTone.tone)
            )
            .filter_by(organization_id=org_id, is_active=True)
            .all()
        )

        result = []
        for org_agent in org_agents:
            tones = [{"id": str(t.tone.id), "name": t.tone.name} for t in org_agent.tones if t.tone]

            result.append({
                "agent_id": str(org_agent.agent_id),
                "accent": {"id": str(org_agent.accent.id), "name": org_agent.accent.name} if org_agent.accent else None,
                "gender": {"id": str(org_agent.gender.id), "name": org_agent.gender.name} if org_agent.gender else None,
                "tones": tones
            })

        return result
    except Exception as e:
        logger.error(f"Error getting organization agents: {e}")
        return []
    finally:
        session.close()
        ScopedSession.remove()


def get_business_agents(business_id: str):
    """
    Get all agents assigned to a business (business-level access control)
    Business agents inherit preferences from organization level

    Args:
        business_id: UUID of the business

    Returns:
        List of agent IDs
    """
    session = ScopedSession()
    try:
        business_agents = (
            session.query(BusinessAgent)
            .filter_by(business_id=business_id, is_active=True)
            .all()
        )

        return [str(ba.agent_id) for ba in business_agents]
    except Exception as e:
        logger.error(f"Error getting business agents: {e}")
        return []
    finally:
        session.close()
        ScopedSession.remove()


def get_agents_with_user_context(
    user_id: str,
    user_role: str = None,
    status: str = None,
    search: str = None,
    agent_type: str = None,
    page: int = 1,
    page_size: int = 10,
):
    """
    Get agents for a user with their organization/business context and preferences.
    This is a comprehensive handler that combines agent filtering with preference resolution.

    Args:
        user_id: User's UUID
        user_role: User's role
        status: Filter by agent status
        search: Search term
        agent_type: Filter by agent type
        page: Page number
        page_size: Items per page

    Returns:
        Dictionary with agents list, pagination, and metadata
    """
    try:
        # Get filtered agents based on user context
        agents, total, org_id, business_id = get_all_agents(
            status=status,
            search=search,
            agent_type=agent_type,
            page=page,
            page_size=page_size,
            user_role=user_role,
            user_id=user_id,
        )

        # Build organization/business preferences map
        org_agent_prefs = _get_org_business_preferences(org_id, business_id)

        # Get user's custom preferences
        user_preferences = get_preferences_by_user(user_id)
        preferences_map = {
            pref["agent"]["id"]: pref
            for pref in user_preferences
            if pref.get("agent") and pref["agent"].get("id")
        }

        # Get default preferences
        default_prefs = _get_default_preferences()

        # Build agent list with resolved preferences
        agent_list = []
        for agent in agents:
            agent_data = _build_agent_response(
                agent=agent,
                user_pref=preferences_map.get(str(agent.id)),
                org_pref=org_agent_prefs.get(str(agent.id)),
                default_prefs=default_prefs
            )
            agent_list.append(agent_data)

        return {
            "status": True,
            "agents": agent_list,
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "pages": (total + page_size - 1) // page_size,
            },
        }

    except Exception as e:
        logger.error(f"Error getting agents with user context: {e}")
        return {
            "status": False,
            "message": str(e),
            "agents": [],
            "pagination": {"total": 0, "page": page, "page_size": page_size, "pages": 0}
        }


def _get_org_business_preferences(org_id: str, business_id: str):
    """
    Helper to get organization/business agent preferences.

    Args:
        org_id: Organization ID
        business_id: Business ID

    Returns:
        Dictionary mapping agent_id to preferences
    """
    org_agent_prefs = {}

    if business_id and org_id:
        # Business users inherit org preferences
        org_agents = get_organization_agents_with_preferences(org_id)
        for org_agent in org_agents:
            org_agent_prefs[org_agent["agent_id"]] = org_agent
    elif org_id:
        # Organization users get org agent preferences
        org_agents = get_organization_agents_with_preferences(org_id)
        for org_agent in org_agents:
            org_agent_prefs[org_agent["agent_id"]] = org_agent

    return org_agent_prefs


def _get_default_preferences():
    """
    Helper to get default tone, accent, and gender preferences.

    Returns:
        Dictionary with default preferences
    """
    default_prefs = {
        "tone": None,
        "accent": None,
        "gender": None
    }

    all_tones = get_all_tone()
    if all_tones:
        default_prefs["tone"] = {
            "id": str(all_tones[0].id),
            "name": all_tones[0].name
        }

    all_accents = get_all_accent()
    if all_accents:
        default_prefs["accent"] = {
            "id": str(all_accents[0].id),
            "name": all_accents[0].name
        }

    all_genders = get_all_gender()
    if all_genders:
        default_prefs["gender"] = {
            "id": str(all_genders[0].id),
            "name": all_genders[0].name
        }

    return default_prefs


def _build_agent_response(agent, user_pref, org_pref, default_prefs):
    """
    Helper to build agent response with resolved preferences.

    Priority: User preference > Org/Business preference > Default

    Args:
        agent: Agent model instance
        user_pref: User's custom preferences for this agent
        org_pref: Organization/Business preferences for this agent
        default_prefs: Default preferences

    Returns:
        Dictionary with agent data and resolved preferences
    """
    # Resolve preferences with priority
    user_gender = None
    user_tones = None
    user_accent = None

    if user_pref:
        # User has set custom preferences
        user_gender = user_pref.get("gender")
        user_tones = user_pref.get("tones")
        user_accent = user_pref.get("accent")
    elif org_pref:
        # Use org/business preferences
        user_gender = org_pref.get("gender")
        user_tones = org_pref.get("tones")
        user_accent = org_pref.get("accent")

    # Apply defaults if still None or empty
    if user_gender is None:
        user_gender = default_prefs["gender"]
    if user_tones is None or (isinstance(user_tones, list) and len(user_tones) == 0):
        user_tones = [default_prefs["tone"]] if default_prefs["tone"] else []
    if user_accent is None:
        user_accent = default_prefs["accent"]

    return {
        "id": str(agent.id),
        "name": agent.name,
        "category_id": str(agent.category_id) if agent.category_id else None,
        "category_name": agent.category.name if agent.category else None,
        "type": agent.type,
        "status": "active" if agent.is_active else "deactivated",
        "created_at": agent.created_at.isoformat(),
        "prompts": [
            {
                "id": str(prompt.id),
                "text": prompt.prompt,
                "created_at": prompt.created_at.isoformat(),
            }
            for prompt in agent.prompts
        ],
        "user_gender": user_gender,
        "user_tones": user_tones,
        "user_accent": user_accent,
    }


def get_all_agents_with_user_assignment_flags(
    user_id: str,
    status: str = None,
    search: str = None,
    agent_type: str = None,
    page: int = 1,
    page_size: int = 10,
):
    """
    Get all agents in the system with flags indicating if each agent is assigned to a specific user.
    This is used for super admin to manage user agent assignments.

    Args:
        user_id: UUID of the user to check assignments against
        status: Filter by agent status (active/deactivated)
        search: Search by agent or category name
        agent_type: Filter by agent type (predefined/custom)
        page: Page number
        page_size: Number of items per page

    Returns:
        Tuple of (agents list with assignment flags, total count, user_name)
    """
    session = ScopedSession()
    try:
        # Get user's name from UserProfile
        user_profile = session.query(UserProfile).filter_by(user_id=user_id).first()
        user_name = None
        if user_profile:
            user_name = get_full_name(user_profile.first_name, user_profile.last_name)

        # Get user's current agent assignments
        user_assignments = get_user_assigned_agents(user_id)
        assigned_ids = set(user_assignments["assigned_agent_ids"])
        removed_ids = set(user_assignments["removed_agent_ids"])

        # Build base query - get ALL agents in the system
        query = session.query(Agent).options(
            joinedload(Agent.category), joinedload(Agent.prompts)
        )

        # Filter by status
        if status:
            if status.lower() == "active":
                query = query.filter(Agent.is_active.is_(True))
            elif status.lower() == "deactivated":
                query = query.filter(Agent.is_active.is_(False))

        # Filter by type
        if agent_type:
            query = query.filter(func.lower(Agent.type) == agent_type.lower())

        # Search by name or category
        if search:
            search_term = f"%{search.lower()}%"
            query = query.join(Category, isouter=True).filter(
                or_(
                    func.lower(Agent.name).like(search_term),
                    func.lower(Category.name).like(search_term),
                )
            )

        total = query.count()
        agents = query.offset((page - 1) * page_size).limit(page_size).all()

        # Build response with assignment flags
        agents_with_flags = []
        for agent in agents:
            agent_id = str(agent.id)

            # Determine assignment status
            is_assigned = agent_id in assigned_ids
            is_removed = agent_id in removed_ids

            agent_data = {
                "id": agent_id,
                "name": agent.name,
                "category_id": str(agent.category_id) if agent.category_id else None,
                "category_name": agent.category.name if agent.category else None,
                "type": agent.type,
                "status": "active" if agent.is_active else "deactivated",
                "created_at": agent.created_at.isoformat(),
                "prompts": [
                    {
                        "id": str(prompt.id),
                        "text": prompt.prompt,
                        "created_at": prompt.created_at.isoformat(),
                    }
                    for prompt in agent.prompts
                ],
                "is_assigned_to_user": is_assigned,  # True if custom agent assigned to user
                "is_removed_from_user": is_removed,  # True if predefined agent removed from user
            }
            agents_with_flags.append(agent_data)

        return agents_with_flags, total, user_name

    except Exception as e:
        logger.error(f"Error getting agents with user assignment flags: {e}")
        return [], 0, None
    finally:
        session.close()
        ScopedSession.remove()
