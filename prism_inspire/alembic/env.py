from logging.config import fileConfig
import os
import sys

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from dotenv import load_dotenv


from alembic import context

load_dotenv()  # Load environment variables from .env file
config = context.config

script_loc = context.config.get_main_option("script_location") or "alembic"
versions_dir = os.path.join(script_loc, "versions")
os.makedirs(versions_dir, exist_ok=True)

init_py = os.path.join(versions_dir, "__init__.py")
if not os.path.exists(init_py):
    open(init_py, "a").close()
    
db_url = os.getenv("ALEMBIC_DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# 4) configure logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
    

# 5) rest of your sys.path / metadata imports…
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from prism_inspire.db.base import Base
from users import models as user_models  # noqa
from ai import models as ai_models        # noqa
target_metadata = Base.metadata

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
