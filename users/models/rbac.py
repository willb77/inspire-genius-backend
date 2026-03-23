import enum
from sqlalchemy import (
    Column, String, Boolean,
    DateTime, func, ForeignKey, Enum
)
from prism_inspire.db.base import Base
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

USERS_USER_ID_FK = "users.user_id"


class RoleLevelEnum(enum.Enum):
    SYSTEM = "system"
    ORGANIZATION = "organization"
    BUSINESS = "business"


class Roles(Base):
    """
    Model to represent roles
    """
    __tablename__ = "roles"
    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String, nullable=False)
    role_level = Column(
        Enum(RoleLevelEnum),
        nullable=False,
        default=RoleLevelEnum.BUSINESS
    )
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

    user_profiles = relationship("UserProfile", back_populates="role_rel")
    role_permissions = relationship("RolePermission", back_populates="role")


class Permissions(Base):
    """
    Model to represent permissions
    """
    __tablename__ = "permissions"
    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=func.now()
    )
    updated_at = Column(
        DateTime,
        default=func.now(),
        server_onupdate=func.now(),
        onupdate=func.now(),
    )
    created_by = Column(UUID(as_uuid=True), ForeignKey(USERS_USER_ID_FK))
    is_deleted = Column(Boolean, default=False)

    role_permissions = relationship("RolePermission", back_populates="permission")


class Groups(Base):
    """
    Model to represent groups
    """
    __tablename__ = "groups"
    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String, nullable=False)
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


class GroupPermission(Base):
    """
    Model to represent group level permissions
    """
    __tablename__ = "group_permission"
    id = Column(UUID(as_uuid=True), primary_key=True)
    group_id = Column(
        UUID(as_uuid=True), ForeignKey("groups.id")
    )
    permission_id = Column(
        UUID(as_uuid=True), ForeignKey("permissions.id")
    )
    created_at = Column(
        DateTime(timezone=True), default=func.now()
    )
    updated_at = Column(
        DateTime,
        default=func.now(),
        server_onupdate=func.now(),
        onupdate=func.now(),
    )
    created_by = Column(UUID(as_uuid=True), ForeignKey(USERS_USER_ID_FK))
    is_deleted = Column(Boolean, default=False)


class RolePermission(Base):
    """
    Model to represent role level permissions
    """
    __tablename__ = "role_permission"
    id = Column(UUID(as_uuid=True), primary_key=True)
    role_id = Column(
        UUID(as_uuid=True), ForeignKey("roles.id")
    )
    permission_id = Column(
        UUID(as_uuid=True), ForeignKey("permissions.id")
    )
    created_at = Column(
        DateTime(timezone=True), default=func.now()
    )
    updated_at = Column(
        DateTime,
        default=func.now(),
        server_onupdate=func.now(),
        onupdate=func.now(),
    )
    created_by = Column(UUID(as_uuid=True), ForeignKey(USERS_USER_ID_FK))
    is_deleted = Column(Boolean, default=False)

    role = relationship("Roles", back_populates="role_permissions")
    permission = relationship("Permissions", back_populates="role_permissions")

