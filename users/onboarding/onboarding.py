from fastapi import APIRouter, Depends
from fastapi_utils.cbv import cbv
from prism_inspire.core.log_config import logger
from users.auth import verify_token
from users.response import (
    SUCCESS_CODE,
    SOMETHING_WENT_WRONG,
    NOT_FOUND,
    VALIDATION_ERROR_CODE,
    create_response,
)
from users.onboarding.req_resp_parser import (
    OnboardingProfileRequest,
    ProfileUpdateRequest,
)
from users.onboarding.schema import (
    create_user_profile,
    update_user_profile,
)

went_wrong = "Something went wrong, please try again later"

onboarding_route = APIRouter(
    prefix="/onboarding",
    tags=["Onboarding"]
)


@cbv(onboarding_route)
class OnboardingView:
    @onboarding_route.post("/profile")
    def create_profile(
        self,
        profile_request: OnboardingProfileRequest,
        user_data: dict = Depends(verify_token),
    ):
        """
        Create user profile during onboarding.
        This endpoint should be called after user registration to complete the profile.
        """
        try:
            user_id = user_data["sub"]

            result = create_user_profile(
                user_id=user_id,
                first_name=profile_request.first_name,
                last_name=profile_request.last_name,
                date_of_birth=profile_request.date_of_birth,
                additional_info=profile_request.additional_info,
            )

            if result["status"]:
                return create_response(
                    message=result["message"],
                    status=True,
                    error_code=SUCCESS_CODE,
                    data=result["profile"],
                    status_code=200
                )
            else:
                # Determine appropriate HTTP status code and error code
                error_type = result.get("error_type", "")
                if error_type == "not_found":
                    http_status = 404
                    error_code = NOT_FOUND
                elif error_type == "validation_error":
                    http_status = 400
                    error_code = VALIDATION_ERROR_CODE
                else:
                    http_status = 500
                    error_code = SOMETHING_WENT_WRONG

                return create_response(
                    message=result["message"],
                    status=False,
                    error_code=error_code,
                    status_code=http_status
                )

        except Exception as e:
            logger.error(f"Error in create_profile endpoint: {str(e)}")
            return create_response(
                message=went_wrong,
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=500
            )

    @onboarding_route.put("/profile")
    def update_profile(
        self,
        profile_request: ProfileUpdateRequest,
        user_data: dict = Depends(verify_token),
    ):
        """
        Update user profile.
        Allows updating any of the profile fields individually or in combination.
        """
        try:
            user_id = user_data["sub"]

            result = update_user_profile(
                user_id=user_id,
                first_name=profile_request.first_name,
                last_name=profile_request.last_name,
                date_of_birth=profile_request.date_of_birth,
                additional_info=profile_request.additional_info,
            )

            if result["status"]:
                return create_response(
                    message=result["message"],
                    status=True,
                    error_code=SUCCESS_CODE,
                    data=result["profile"],
                    status_code=200
                )
            else:
                # Determine appropriate HTTP status code and error code
                error_type = result.get("error_type", "")
                if error_type == "not_found":
                    http_status = 404
                    error_code = NOT_FOUND
                elif error_type == "validation_error":
                    http_status = 400
                    error_code = VALIDATION_ERROR_CODE
                else:
                    http_status = 500
                    error_code = SOMETHING_WENT_WRONG

                return create_response(
                    message=result["message"],
                    status=False,
                    error_code=error_code,
                    status_code=http_status
                )

        except Exception as e:
            logger.error(f"Error in update_profile endpoint: {str(e)}")
            return create_response(
                message=went_wrong,
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=500
            )

