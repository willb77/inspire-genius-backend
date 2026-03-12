from sqlalchemy.orm import declarative_base
from sqlalchemy import MetaData

# Recommended naming convention for constraints for Alembic autogenerate.
# See: https://alembic.sqlalchemy.org/en/latest/naming.html
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata_obj = MetaData(naming_convention=NAMING_CONVENTION)
Base = declarative_base(metadata=metadata_obj)

# This Base will be imported by your models (e.g., users.models.User)
# and by alembic/env.py to get target_metadata for autogeneration.
