from pydantic_settings import BaseSettings
from pydantic import field_validator, validator
import logging


import os
from pydantic_settings import BaseSettings


def _validate_url_security(name: str, v: str) -> str:
    """Ensure URL uses HTTPS unless it's localhost/dev."""
    if v and v.startswith("http://"):
        if not any(local in v for local in ("localhost", "127.0.0.1", "0.0.0.0")):
            logger = logging.getLogger(__name__)
            logger.error(f"{name} uses insecure HTTP protocol: {v}")
            raise ValueError(f"{name} must use HTTPS protocol for security. "
                             "HTTP is only allowed for localhost/dev.")
        logging.getLogger(__name__).info(f"HTTP allowed for local development: {v}")
    return v


class Settings(BaseSettings):
    PROJECT_NAME: str = "Prism Inspire"
    API_V1_STR: str = "/v1"
    DOCS_URL: str = "/docs"
    S3_DOCUMENTS_PREFIX: str = "documents/"
    
    DATABASE_URL: str 
    ALEMBIC_DATABASE_URL: str
    VECTOR_PG_DATABASE_URL: str
    OPENAI_API_KEY: str
    VOYAGEAI_API_KEY: str
    GEMINI_API_KEY: str 
    
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_SESSION_TOKEN: str | None = None 
    
    COGNITO_USER_POOL_ID: str
    COGNITO_CLIENT_ID: str
    COGNITO_CLIENT_SECRET: str
    COGNITO_DOMAIN: str

    LOCATION_AWS_REGION: str = "us-east-1"
    TRACKER_NAME: str
    COLLECTION_NAME: str
    
    S3_BUCKET_NAME: str
    S3_PROFILE_PHOTOS_PREFIX: str = "profile-photos/"

    # Backblaze B2 Settings
    B2_KEY_ID: str = "00536846b4626ee0000000001"
    B2_APPLICATION_KEY: str = "K005hkp6RIbNf0ycfsXPw95Ayw1C9xo"
    B2_BUCKET_NAME: str = "prism-coach-knbs-files"
    B2_ENDPOINT_URL: str = "https://s3.us-east-005.backblazeb2.com"

    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str
    
    FACEBOOK_CLIENT_ID: str
    FACEBOOK_CLIENT_SECRET: str
    FACEBOOK_REDIRECT_URI: str
    
    BASE_URL: str
    FRONTEND_URL: str
    ALLOWED_ORIGINS: str
    
    MILVUS_URI: str
    MILVUS_USER: str
    MILVUS_PASSWORD: str
    MILVUS_COLLECTION_NAME: str

    # JWT Secret Key for password reset tokens
    SECRET_KEY: str

    @field_validator("BASE_URL")
    @classmethod
    def validate_base_url(cls, v):
        return _validate_url_security("BASE_URL", v)

    @field_validator("FRONTEND_URL")
    @classmethod
    def validate_frontend_url(cls, v):
        return _validate_url_security("FRONTEND_URL", v)

    class Config:
        case_sensitive = True
        env_file = ".env"


settings = Settings()
