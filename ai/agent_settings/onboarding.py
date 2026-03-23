from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi_utils.cbv import cbv

from ai.agent_settings.req_resp_parser import (
    AgentPreferenceRequest,
    AssignAgentsToUserRequest,
    CreateAgentRequest,
    CreateCategoryRequest,
    UpdateAgentPreference,
    UpdateAgentRequest,
)
from ai.agent_settings.schema import (
    assign_agents_to_user,
    create_agent,
    create_category,
    deactivate_agent,
    get_agents_with_user_context,
    get_all_accent,
    get_all_agents,
    get_all_agents_with_user_assignment_flags,
    get_all_category,
    get_all_gender,
    get_all_tone,
    get_preferences_by_user,
    get_user_assigned_agents,
    set_user_agent_preference,
    update_agent,
)
from prism_inspire.core.log_config import logger
from users.auth import verify_token
from users.aws_wrapper.cognito_utils import (
    get_cognito_username_by_user_id,
    update_cognito_user_attributes,
)
from users.decorators import require_super_admin_role
from users.response import (
    NOT_FOUND,
    SOMETHING_WENT_WRONG,
    SUCCESS_CODE,
    VALIDATION_ERROR_CODE,
    create_response,
)

went_wrong = "Something went wrong, please try again later"

agents_settings = APIRouter(prefix="/agents-settings", tags=["Agent Settings"])


@cbv(agents_settings)
class UserAgentPreferenceView:
    @agents_settings.post("/preferences")
    def set_agent_preference(
        self,
        preference_request: AgentPreferenceRequest,
        user_data: dict = Depends(verify_token),
    ):
        try:
            user_id = user_data["sub"]
            preference_ids = []

            for pref in preference_request.preferences:
                pref_id = set_user_agent_preference(
                    user_id=user_id,
                    agent_id=pref.agent_id,
                    tone_ids=pref.tone_ids,
                    accent_id=pref.accent_id,
                    gender_id=pref.gender_id,
                )
                if pref_id:
                    preference_ids.append(str(pref_id))

            if preference_ids:
                return create_response(
                    message="Agent preferences saved successfully",
                    status=True,
                    error_code=SUCCESS_CODE,
                    data={"preference_ids": preference_ids},
                )

            return create_response(
                message="Failed to save preferences",
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=500
            )
        except Exception as e:
            logger.error(e)
            return create_response(
                message=went_wrong,
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=500
            )

    @agents_settings.put("/preferences/{agent_id}")
    def update_agent_preference(
        self,
        agent_id: UUID,
        update_request: UpdateAgentPreference,
        user_data: dict = Depends(verify_token),
    ):
        try:
            user_id = user_data["sub"]
            updated = set_user_agent_preference(
                user_id=user_id,
                agent_id=agent_id,
                tone_ids=update_request.tone_ids,
                accent_id=update_request.accent_id,
                gender_id=update_request.gender_id,
            )

            if updated:
                return create_response(
                    message="Agent preference updated successfully",
                    status=True,
                    error_code=SUCCESS_CODE,
                    data={"preference_id": str(updated)},
                )
            return create_response(
                message="Preference not found for update",
                status=False,
                error_code=NOT_FOUND,
                status_code=404
            )
        except Exception as e:
            logger.error(e)
            return create_response(
                message=went_wrong,
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=500
            )

    @agents_settings.get("/preferences")
    def get_user_preferences(self, user_data: dict = Depends(verify_token)):
        try:
            user_id = user_data["sub"]
            prefs = get_preferences_by_user(user_id)

            return create_response(
                message="Preferences fetched",
                status=True,
                error_code=SUCCESS_CODE,
                data={"preferences": prefs},
            )
        except Exception as e:
            logger.error(e)
            return create_response(
                message=went_wrong,
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=500
            )


@cbv(agents_settings)
class AgentView:
    @agents_settings.get("/agents")
    def get_all_agents_api(
        self,
        status: str = None,
        search: str = None,
        type: str = None,
        page: int = 1,
        page_size: int = 10,
        user_data: dict = Depends(verify_token)
    ):
        """
        DEPRECATED: This is the old API endpoint for getting agents.
        Please use /v1/agents-settings/user/agents instead.
        This endpoint will be removed once the new endpoint is fully adopted.
        """
        try:
            user_id = user_data["sub"]

            agents, total, org_id, business_id = get_all_agents(
                status=status,
                search=search,
                agent_type=type,
                page=page,
                page_size=page_size,
                user_role=user_data.get("user_role"),
                user_id=user_id
            )

            # Get user preferences for all agents
            user_preferences = get_preferences_by_user(user_id)

            # Create a mapping of agent_id to preferences
            preferences_map = {}
            for pref in user_preferences:
                if pref.get("agent") and pref["agent"].get("id"):
                    preferences_map[pref["agent"]["id"]] = pref

            # Get default values for tone, accent, and gender (first record from each table)
            default_tone = None
            default_accent = None
            default_gender = None

            all_tones = get_all_tone()
            if all_tones:
                default_tone = {
                    "id": str(all_tones[0].id),
                    "name": all_tones[0].name
                }

            all_accents = get_all_accent()
            if all_accents:
                default_accent = {
                    "id": str(all_accents[0].id),
                    "name": all_accents[0].name
                }

            all_genders = get_all_gender()
            if all_genders:
                default_gender = {
                    "id": str(all_genders[0].id),
                    "name": all_genders[0].name
                }

            data = []
            for agent in agents:
                agent_id_str = str(agent.id)
                user_pref = preferences_map.get(agent_id_str)

                # Extract user's selected preferences for this agent
                user_gender = None
                user_tones = None
                user_accent = None

                if user_pref:
                    user_gender = user_pref.get("gender")
                    user_tones = user_pref.get("tones")
                    user_accent = user_pref.get("accent")

                # Apply defaults if values are None or empty
                if user_gender is None:
                    user_gender = default_gender
                
                if user_tones is None or (isinstance(user_tones, list) and len(user_tones) == 0):
                    user_tones = [default_tone] if default_tone else []
                
                if user_accent is None:
                    user_accent = default_accent

                data.append(
                    {
                        "id": agent_id_str,
                        "name": agent.name,
                        "category_id": (
                            str(agent.category_id) if agent.category_id else None
                        ),
                        "category_name": (
                            agent.category.name if agent.category else None
                        ),
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
                )

            return create_response(
                message="Agents retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={
                    "agents": data,
                    "pagination": {
                        "total": total,
                        "page": page,
                        "page_size": page_size,
                        "pages": (total + page_size - 1) // page_size,
                    },
                },
            )

        except Exception as e:
            logger.error(f"Error fetching agents: {e}")
            return create_response(
                message=went_wrong,
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

    @agents_settings.get("/user/agents")
    def get_all_user_agents_api(
        self,
        status: str = None,
        search: str = None,
        type: str = None,
        page: int = 1,
        page_size: int = 10,
        user_data: dict = Depends(verify_token)
    ):
        """
        Get all agents available to the current user with their preferences.

        This endpoint considers:
        - User's organization/business context
        - Custom agent assignments by super admin
        - Voice preferences (user > org > default)

        Returns agents filtered by user's access level with resolved preferences.

        As Super Admin Returns all agents with preferences.
        """
        try:
            user_id = user_data["sub"]
            user_role = user_data.get("user_role")

            # Use the comprehensive handler
            result = get_agents_with_user_context(
                user_id=user_id,
                user_role=user_role,
                status=status,
                search=search,
                agent_type=type,
                page=page,
                page_size=page_size,
            )

            if not result["status"]:
                return create_response(
                    message=result.get("message", went_wrong),
                    error_code=SOMETHING_WENT_WRONG,
                    status=False,
                    status_code=500
                )

            return create_response(
                message="Agents retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={
                    "agents": result["agents"],
                    "pagination": result["pagination"],
                },
            )

        except Exception as e:
            logger.error(f"Error fetching agents: {e}")
            return create_response(
                message=went_wrong,
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

    @agents_settings.get("/user/{user_id}/agents")
    def get_user_agent_configurations_api(
        self,
        user_id: UUID,
        status: str = None,
        search: str = None,
        type: str = None,
        page: int = 1,
        page_size: int = 10,
        user_data: dict = Depends(require_super_admin_role())
    ):
        """
        Get all agents with their configuration status for a specific user (Super Admin only).

        This endpoint retrieves all agents in the system with information about which ones are
        configured for a specific user:
        - Custom agents that have been enabled for the user
        - Predefined agents that have been disabled for the user

        Args:
            user_id: UUID of the user to check configurations for
            status: Filter by agent status (active/deactivated)
            search: Search by agent or category name
            type: Filter by agent type (predefined/custom)
            page: Page number
            page_size: Number of items per page

        Returns all agents with their configuration status for the specified user.
        """
        try:
            agents_with_flags, total, user_name = get_all_agents_with_user_assignment_flags(
                user_id=str(user_id),
                status=status,
                search=search,
                agent_type=type,
                page=page,
                page_size=page_size,
            )

            return create_response(
                message="Agents with user assignment flags retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={
                    "user_name": user_name,
                    "agents": agents_with_flags,
                    "pagination": {
                        "total": total,
                        "page": page,
                        "page_size": page_size,
                        "pages": (total + page_size - 1) // page_size,
                    },
                },
            )

        except Exception as e:
            logger.error(f"Error fetching agents with user assignment flags: {e}")
            return create_response(
                message=went_wrong,
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

    @agents_settings.post("/agents")
    def create_agent_api(
        self,
        agent_request: CreateAgentRequest,
        user_data: dict = Depends(require_super_admin_role()),
    ):
        """Create a new agent with prompt"""
        try:
            result = create_agent(
                {
                    "name": agent_request.name,
                    "category_name": agent_request.category_name,
                    "prompt": agent_request.prompt,
                }
            )
            if not result["status"]:
                return create_response(
                    message=result["message"],
                    error_code=VALIDATION_ERROR_CODE,
                    status=False,
                    status_code=400
                )

            return create_response(
                message=result["message"],
                error_code=SUCCESS_CODE,
                status=True,
                data={"agent_id": result["agent_id"]},
            )

        except Exception as e:
            logger.error(f"Error creating agent: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @agents_settings.put("/agents")
    def update_agent_api(
        self,
        agent_id: UUID,
        agent_request: UpdateAgentRequest,
        user_data: dict = Depends(require_super_admin_role()),
    ):
        """Update an agent's prompt"""
        try:
            result = update_agent(
                {
                    "id": agent_id,
                    "name": agent_request.name,
                    "category_name": agent_request.category_name,
                    "prompt": agent_request.prompt,
                    "status": agent_request.status,
                }
            )

            if not result["status"]:
                return create_response(
                    message=result["message"],
                    error_code=VALIDATION_ERROR_CODE,
                    status=False,
                    status_code=400
                )

            return create_response(
                message=result["message"], error_code=SUCCESS_CODE, status=True
            )

        except Exception as e:
            logger.error(f"Error updating prompt: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @agents_settings.delete("/deactivate", response_model=dict)
    def deactivate_agent_api(
        self, agent_id: UUID, user_data: dict = Depends(require_super_admin_role())
    ):
        """Deactivate an agent by ID (set is_active = False)"""
        try:
            result = deactivate_agent(agent_id)

            if not result["status"]:
                return create_response(
                    message=result["message"],
                    error_code=VALIDATION_ERROR_CODE,
                    status=False,
                    status_code=400
                )

            return create_response(
                message=result["message"],
                error_code=SUCCESS_CODE,
                status=True,
                data={"agent_id": result["agent_id"]},
            )
        except Exception as e:
            logger.error(f"Error deactivating agent: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @agents_settings.post("/user/agents/assign")
    def assign_agents_to_user_api(
        self,
        assignment_request: AssignAgentsToUserRequest,
        user_data: dict = Depends(require_super_admin_role()),
    ):
        """
        Assign or remove agents for a specific user (Super Admin only).

        Use Cases:
        - Assign custom agents to a user (is_active=True)
        - Remove/block predefined agents from a user (is_active=False)

        This allows fine-grained control over which agents each user can access.
        """
        try:
            result = assign_agents_to_user(
                user_id=str(assignment_request.user_id),
                agent_ids=[str(aid) for aid in assignment_request.agent_ids],
                is_active=assignment_request.is_active
            )

            if not result["status"]:
                return create_response(
                    message=result["message"],
                    error_code=VALIDATION_ERROR_CODE,
                    status=False,
                    status_code=400
                )

            return create_response(
                message=result["message"],
                error_code=SUCCESS_CODE,
                status=True,
                data={"assignment_ids": result["assignment_ids"]},
            )
        except Exception as e:
            logger.error(f"Error assigning agents to user: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @agents_settings.get("/user-assignments/{user_id}")
    def get_user_agent_assignments_api(
        self,
        user_id: UUID,
        user_data: dict = Depends(require_super_admin_role()),
    ):
        """
        Get all agent assignments for a specific user (Super Admin only).

        Returns:
        - assigned_agent_ids: Custom agents explicitly assigned to the user
        - removed_agent_ids: Predefined agents explicitly removed from the user
        """
        try:
            result = get_user_assigned_agents(str(user_id))

            return create_response(
                message="User agent assignments retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data=result,
            )
        except Exception as e:
            logger.error(f"Error getting user assignments: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )


@cbv(agents_settings)
class ToneView:
    @agents_settings.get("/tone")
    def get_all_tone_api(self):
        try:
            tones = get_all_tone()

            data = [
                {
                    "id": str(tone.id),
                    "name": tone.name,
                    "created_at": tone.created_at.isoformat(),
                }
                for tone in tones
            ]

            return create_response(
                message="Tones retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={"Tones": data},
            )

        except Exception as e:
            logger.error(f"Error fetching tones: {e}")
            return create_response(
                message=went_wrong,
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )


@cbv(agents_settings)
class AccentView:
    @agents_settings.get("/accent")
    def get_all_accent_api(self):
        try:
            accents = get_all_accent()

            data = [
                {
                    "id": str(accent.id),
                    "name": accent.name,
                    "created_at": accent.created_at.isoformat(),
                }
                for accent in accents
            ]

            return create_response(
                message="Language retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={"Tones": data},
            )

        except Exception as e:
            logger.error(f"Error fetching Language: {e}")
            return create_response(
                message=went_wrong,
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )


@cbv(agents_settings)
class GenderView:
    @agents_settings.get("/gender")
    def get_all_gender_api(self):
        try:
            genders = get_all_gender()

            data = [
                {
                    "id": str(gender.id),
                    "name": gender.name,
                    "created_at": gender.created_at.isoformat(),
                }
                for gender in genders
            ]

            return create_response(
                message="Genders retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={"Genders": data},
            )

        except Exception as e:
            logger.error(f"Error fetching Genders: {e}")
            return create_response(
                message=went_wrong,
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )


@cbv(agents_settings)
class CategoryView:
    @agents_settings.get("/category")
    def get_all_category_api(self):
        try:
            categoryies = get_all_category()

            data = [
                {
                    "id": str(category.id),
                    "name": category.name,
                    "display_name": category.display_name,
                    "type": category.type,
                    "created_at": category.created_at.isoformat(),
                }
                for category in categoryies
            ]

            return create_response(
                message="Category retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={"Tones": data},
            )

        except Exception as e:
            logger.error(f"Error fetching Category: {e}")
            return create_response(
                message=went_wrong,
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

    @agents_settings.post("/category")
    def add_category_api(
        self,
        category_request: CreateCategoryRequest,
        user_data: dict = Depends(require_super_admin_role()),
    ):
        """Create a new category"""
        try:
            category_data = {
                "name": category_request.name,
                "display_name": category_request.display_name,
                "type": category_request.type,
            }
            result = create_category(category_data)
            if not result["status"]:
                return create_response(
                    message=result["message"],
                    error_code=VALIDATION_ERROR_CODE,
                    status=False,
                    status_code=400
                )

            return create_response(
                message=result["message"],
                error_code=SUCCESS_CODE,
                status=True,
                data={"category_id": result["category_id"]},
            )
        except Exception as e:
            logger.error(f"Error create category: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )
