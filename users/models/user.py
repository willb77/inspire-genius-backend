from sqlalchemy import (
    Column, Date, Integer, String, Boolean,
    DateTime, func, Enum, ForeignKey, Numeric
)
from sqlalchemy.orm import relationship
from prism_inspire.db.base import Base
import enum
from sqlalchemy.dialects.postgresql import UUID
from users.auth_service.utils import get_full_name

DELETE = "all, delete-orphan"
USER_ID = "users.user_id"
ORGANIZATION_ID = "organization.id"
PROFILE_ID = "user_profiles.id"

class AuthProviderEnum(enum.Enum):
    cognito = "cognito"
    google = "google"
    facebook = "facebook"


class BusinessTypeEnum(enum.Enum):
    CORPORATE = "corporate"
    EDUCATION = "education"


class OrganizationTypeEnum(enum.Enum):
    BOTH = "both"
    EDUCATION = "education"
    CORPORATE = "corporate"


class Users(Base):
    __tablename__ = "users"

    user_id = Column(UUID(as_uuid=True), primary_key=True)
    email = Column(String(150), nullable=False, unique=True)
    password = Column(String(255), nullable=True)
    auth_provider = Column(
        Enum(AuthProviderEnum, name="auth_provider_enum"),
        nullable=False,
        default=AuthProviderEnum.cognito
    )
    is_email_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now()
    )
    is_deleted = Column(Boolean, default=False)
    # One-to-one relationship to UserProfile
    profile = relationship(
        "UserProfile",
        back_populates="user",
        foreign_keys="UserProfile.user_id",
        uselist=False, cascade=DELETE
    )
    # Issues reported by this user
    reported_issues = relationship("Issue", foreign_keys="Issue.reported_by", back_populates="reporter")
    files = relationship(
        "File", back_populates="user",
        cascade=DELETE
    )

    @property
    def has_profile(self):
        """Check if user has completed profile"""
        return self.profile is not None

    @property
    def is_oauth_user(self):
        """Check if user signed up via OAuth"""
        return self.auth_provider in ['google', 'facebook']

    @property
    def display_name(self):
        """Get display name from profile or email"""
        if self.profile and self.profile.full_name:
            return self.profile.full_name
        return self.email.split('@')[0]


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey(USER_ID, ondelete="CASCADE"),
        nullable=False, unique=True
    )
    first_name = Column(String(50), nullable=True)
    last_name = Column(String(50), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    additional_info = Column(String(500), nullable=True)
    mobile_number = Column(String(15), nullable=True)
    profile_photo = Column(String(255), nullable=True)
    is_primary = Column(Boolean, default=False)
    role = Column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=True
    )
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey(ORGANIZATION_ID, ondelete="CASCADE"),
        nullable=True
    )
    business_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business.id", ondelete="CASCADE"),
        nullable=True
    )
    user_group = Column(
        UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=True
    )

    assigned_by = Column(UUID(as_uuid=True), ForeignKey(USER_ID))
    assigned_at = Column(DateTime(timezone=True), default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)

    is_profile_complete = Column(Boolean, default=False)
    has_submitted_survey = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now()
    )

    @property
    def full_name(self):
        """Get full name from first_name and last_name"""
        return get_full_name(self.first_name, self.last_name)
    # One-to-one relationship back to Users
    user = relationship("Users", back_populates="profile", foreign_keys=[user_id])
    role_rel = relationship("Roles", back_populates="user_profiles")
    organization = relationship("Organization", back_populates="members")
    business = relationship("Business", back_populates="members")
    assigned_by_user = relationship("Users", foreign_keys=[assigned_by])
    
    # Profile extensions
    employee_profile = relationship("EmployeeProfile", back_populates="user_profile", foreign_keys="EmployeeProfile.user_profile_id", uselist=False)
    teacher_profile = relationship("TeacherProfile", back_populates="user_profile", uselist=False)
    student_profile = relationship("StudentProfile", back_populates="user_profile", foreign_keys="StudentProfile.user_profile_id", uselist=False)

class Organization(Base):
    __tablename__ = "organization"
    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String(150), nullable=False)
    contact = Column(String(15), nullable=False)
    email = Column(String(150), nullable=True)
    address = Column(String(500), nullable=True)
    website_url = Column(String(255), nullable=True)
    logo = Column(String(500), nullable=True)  # Will store logo file path/URL when implemented
    type = Column(
        Enum(OrganizationTypeEnum),
        nullable=False,
        default=OrganizationTypeEnum.BOTH
    )
    is_onboarded = Column(Boolean, default=False)
    status = Column(Boolean, default=True)
    created_at = Column(
        DateTime(timezone=True), default=func.now()
    )
    updated_at = Column(
        DateTime,
        default=func.now(),
        server_onupdate=func.now(),
        onupdate=func.now(),
    )
    is_deleted = Column(Boolean, default=False)

    businesses = relationship("Business", back_populates="organization", cascade=DELETE)
    members = relationship("UserProfile", back_populates="organization")
    admins = relationship("OrganizationAdmin", back_populates="organization")
    assigned_agents = relationship("OrganizationAgent", back_populates="organization", cascade=DELETE)
    licenses = relationship("License", back_populates="organization")


# TO stored the assign admin details of particular organization 
class OrganizationAdmin(Base):
    __tablename__ = "organization_admin"
    
    id = Column(UUID(as_uuid=True), primary_key=True)
    organization_id = Column(
        UUID(as_uuid=True), 
        ForeignKey(ORGANIZATION_ID, ondelete="CASCADE")
    )
    user_id = Column(
        UUID(as_uuid=True), 
        ForeignKey(USER_ID, ondelete="CASCADE")
    )
    assigned_by = Column(UUID(as_uuid=True), ForeignKey(USER_ID))
    assigned_at = Column(DateTime(timezone=True), default=func.now())
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime,
        default=func.now(),
        server_onupdate=func.now(),
        onupdate=func.now(),
    )
    
    # Relationships
    organization = relationship("Organization", back_populates="admins")
    user = relationship("Users", foreign_keys=[user_id])
    assigned_by_user = relationship("Users", foreign_keys=[assigned_by])


class Business(Base):
    __tablename__ = "business"

    id = Column(UUID(as_uuid=True), primary_key=True)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey(ORGANIZATION_ID, ondelete="CASCADE"),
        nullable=False
    )
    name = Column(String(150), nullable=False)
    description = Column(String(1000), nullable=True)
    contact_email = Column(String(150), nullable=True)
    contact_phone = Column(String(15), nullable=True)
    business_type = Column(
        Enum(BusinessTypeEnum),
        nullable=False,
        default=BusinessTypeEnum.CORPORATE
    )
    is_onboarded = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime,
        default=func.now(),
        server_onupdate=func.now(),
        onupdate=func.now(),
    )
    is_deleted = Column(Boolean, default=False)
    
    # Relationships
    organization = relationship("Organization", back_populates="businesses")
    members = relationship("UserProfile", back_populates="business")


# Enhancement of profile models based on role
class EmployeeProfile(Base):
    __tablename__ = "employee_profiles"
    
    id = Column(UUID(as_uuid=True), primary_key=True)
    user_profile_id = Column(
        UUID(as_uuid=True),
        ForeignKey(PROFILE_ID, ondelete="CASCADE"),
        nullable=False, unique=True
    )
    employee_id = Column(String(50), nullable=True)
    department = Column(String(100), nullable=True)
    position = Column(String(100), nullable=True)
    salary = Column(Numeric(10, 2), nullable=True)
    hire_date = Column(Date, nullable=True)
    manager_id = Column(UUID(as_uuid=True), ForeignKey(PROFILE_ID))
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now()
    )
    
    user_profile = relationship("UserProfile", back_populates="employee_profile", foreign_keys=[user_profile_id])
    manager = relationship("UserProfile", foreign_keys=[manager_id])


class TeacherProfile(Base):
    __tablename__ = "teacher_profiles"
    
    id = Column(UUID(as_uuid=True), primary_key=True)
    user_profile_id = Column(
        UUID(as_uuid=True),
        ForeignKey(PROFILE_ID, ondelete="CASCADE"),
        nullable=False, unique=True
    )
    teacher_id = Column(String(50), nullable=True)
    subject_specialization = Column(String(100), nullable=True)
    qualification = Column(String(200), nullable=True)
    years_experience = Column(Integer, nullable=True)
    certification = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now()
    )
    
    user_profile = relationship("UserProfile", back_populates="teacher_profile")


class StudentProfile(Base):
    __tablename__ = "student_profiles"
    
    id = Column(UUID(as_uuid=True), primary_key=True)
    user_profile_id = Column(
        UUID(as_uuid=True),
        ForeignKey(PROFILE_ID, ondelete="CASCADE"),
        nullable=False, unique=True
    )
    student_id = Column(String(50), nullable=True)
    grade_level = Column(String(20), nullable=True)
    enrollment_date = Column(Date, nullable=True)
    parent_contact_id = Column(UUID(as_uuid=True), ForeignKey(PROFILE_ID))
    emergency_contact = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now()
    )
    
    user_profile = relationship("UserProfile", back_populates="student_profile", foreign_keys=[user_profile_id])
    parent_contact = relationship("UserProfile", foreign_keys=[parent_contact_id])


class OrganizationAgent(Base):
    """
    Model to represent agent assignments to organizations with preferences
    """
    __tablename__ = "organization_agents"

    id = Column(UUID(as_uuid=True), primary_key=True)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey(ORGANIZATION_ID, ondelete="CASCADE"),
        nullable=False
    )
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False
    )
    assigned_by = Column(UUID(as_uuid=True), ForeignKey(USER_ID))
    assigned_at = Column(DateTime(timezone=True), default=func.now())
    is_active = Column(Boolean, default=True)
    # Agent preferences
    accent_id = Column(UUID(as_uuid=True), ForeignKey("accents.id"), nullable=True)
    gender_id = Column(UUID(as_uuid=True), ForeignKey("genders.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime,
        default=func.now(),
        server_onupdate=func.now(),
        onupdate=func.now(),
    )

    organization = relationship("Organization", back_populates="assigned_agents")
    assigned_by_user = relationship("Users", foreign_keys=[assigned_by])
    accent = relationship("Accent", foreign_keys=[accent_id])
    gender = relationship("Gender", foreign_keys=[gender_id])
    # Many-to-many relationship with Tone through OrganizationAgentPreferenceTone
    tones = relationship("OrganizationAgentPreferenceTone", back_populates="organization_agent", cascade="all, delete-orphan")


class OrganizationAgentPreferenceTone(Base):
    """
    Junction table for many-to-many relationship between OrganizationAgent and Tone
    Similar to UserPreferenceTone but for organization-level agent preferences
    """
    __tablename__ = "organization_agent_preference_tones"

    id = Column(UUID(as_uuid=True), primary_key=True)
    organization_agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organization_agents.id", ondelete="CASCADE"),
        nullable=False
    )
    tone_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tones.id", ondelete="CASCADE"),
        nullable=False
    )
    created_at = Column(DateTime(timezone=True), default=func.now())
    organization_agent = relationship("OrganizationAgent", back_populates="tones")
    tone = relationship("Tone")


class BusinessAgent(Base):
    """
    Model to represent agent access for businesses.
    Business agents inherit settings from parent organization.
    This table only tracks which agents a business has access to.
    """
    __tablename__ = "business_agents"

    id = Column(UUID(as_uuid=True), primary_key=True)
    business_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business.id", ondelete="CASCADE"),
        nullable=False
    )
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False
    )
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime,
        default=func.now(),
        server_onupdate=func.now(),
        onupdate=func.now(),
    )

    business = relationship("Business", backref="assigned_agents")


class InvitationStatusEnum(enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    CANCELLED = "cancelled" # not using now


class UserInvitation(Base):
    """
    Model to represent user invitations with token-based system
    """
    __tablename__ = "user_invitations"

    id = Column(UUID(as_uuid=True), primary_key=True)
    email = Column(String(150), nullable=False)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey(ORGANIZATION_ID, ondelete="CASCADE"),
        nullable=True
    )
    business_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business.id", ondelete="CASCADE"),
        nullable=True
    )
    role_id = Column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False
    )
    invitation_token = Column(String(255), nullable=False, unique=True)
    status = Column(
        Enum(InvitationStatusEnum),
        nullable=False,
        default=InvitationStatusEnum.PENDING
    )
    invited_by = Column(UUID(as_uuid=True), ForeignKey(USER_ID))
    invited_at = Column(DateTime(timezone=True), default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime,
        default=func.now(),
        server_onupdate=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    organization = relationship("Organization")
    business = relationship("Business")
    role = relationship("Roles")
    invited_by_user = relationship("Users", foreign_keys=[invited_by])
