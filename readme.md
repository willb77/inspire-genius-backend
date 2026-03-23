# Project Structure & Setup

This document outlines the basic structure of the project, explains the contents of the main `prism_inspire` application package, and details how to manage database migrations using Alembic.

## Folder Structure Overview

```
.                             # Project Root
├── alembic/                  # Alembic migration scripts and environment
├── alembic.ini               # Alembic configuration file
├── prism_inspire/            # Main application package
│   ├── core/                 # Core settings and configurations
│   │   ├── __init__.py
│   │   └── config.py
│   ├── db/                   # Database session, base models
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── session.py
│   ├── __init__.py           # Makes 'prism_inspire' a package
│   └── main.py               # FastAPI application entry point
├── users/                    # 'users' application module (separate from prism_inspire)
│   ├── __init__.py
│   ├── crud.py
│   ├── models.py
│   ├── router.py
│   └── schemas.py
├── ai/                       # 'ai' application module (separate from prism_inspire)
│   ├── __init__.py
│   ├── crud.py
│   ├── models.py
│   ├── router.py
│   └── schemas.py
└── ...                       # Other project files (e.g., .venv, requirements.txt)
```

### Key Directories

- **`alembic/`**: Contains all Alembic-generated migration scripts and the environment configuration (`env.py`) for database schema management. Located at the project root.
- **`alembic.ini`**: Configuration file for Alembic, located at the project root.
- **`prism_inspire/`**: The **main application package**. Houses the core logic, configurations, and the FastAPI application instance.
- **`users/`**, **`ai/`**: Application-specific modules, each containing its own models, schemas, CRUD operations, and API routes. Structured as separate Python packages at the project root.

## The `prism_inspire` Package Explained

The `prism_inspire/` directory is the heart of the FastAPI application.

- **`prism_inspire/__init__.py`**:  
    An empty file that tells Python to treat the `prism_inspire` directory as a package. This allows you to import modules from within this directory using dot notation (e.g., `from prism_inspire.core import settings`).

- **`prism_inspire/main.py`**:  
    **Application Entry Point**: This is where the main FastAPI application instance is created (e.g., `app = FastAPI()`).  
    **Global Middleware**: Any application-wide middleware (like CORS, error handling) would typically be configured here.  
    **Router Inclusion**: Imports and includes API routers from other modules (like `users.router` and `ai.router`).  
    **Root Endpoint**: Often contains a simple root endpoint (e.g., `@app.get("/")`) for health checks or a welcome message.  
    **Startup/Shutdown Events**: Application lifecycle events (tasks to run on startup or shutdown) can be defined here.

- **`prism_inspire/core/`**:  
    Contains core configuration and settings for the application.

    - **`prism_inspire/core/__init__.py`**: Makes `core` a Python sub-package.
    - **`prism_inspire/core/config.py`**:  
        - **Settings Management**: Defines how application settings are loaded and managed, typically using Pydantic's `BaseSettings`.
        - **Environment Variables**: Loads settings from environment variables, `.env` files, or default values.
        - **Centralized Configuration**: Provides a single source of truth for configurations like database URLs, API keys, project name, debug modes, etc.

- **`prism_inspire/db/`**:  
    Responsible for database-related setup and utilities.

    - **`prism_inspire/db/__init__.py`**: Makes `db` a Python sub-package.
    - **`prism_inspire/db/base.py`**:  
        - **Declarative Base**: Defines the SQLAlchemy `declarative_base()` (often named `Base`). All ORM models in the application (e.g., `User`, `AiTask`) will inherit from this `Base`.
        - **Metadata**: The `Base.metadata` object collects information about all defined tables, which is crucial for Alembic to generate migrations.
        - **(Optional) Naming Conventions**: Can define naming conventions for database constraints to ensure consistency.
    - **`prism_inspire/db/session.py`**:  
        - **Database Engine**: Creates the SQLAlchemy engine (e.g., `create_engine` or `create_async_engine`) using the database URL from the application's configuration.
        - **Session Factory**: Defines a session factory (e.g., `SessionLocal = sessionmaker(...)`) that creates new database sessions.
        - **Dependency for Sessions**: Provides a FastAPI dependency (e.g., `get_db()`) that path operation functions can use to obtain a database session for their requests. This dependency also typically handles closing the session after the request is complete.

## Database Migrations (Alembic)

This project uses [Alembic](https://alembic.sqlalchemy.org/) to handle database schema migrations. All Alembic commands should be run from the **project root directory** (the directory containing `alembic.ini` and the `prism_inspire` folder).

### Prerequisites

- Ensure Alembic is installed (`pip install alembic`).
- Configure your database connection URL in `alembic.ini` (for Alembic's use) and in `prism_inspire/core/config.py` (for the application's use). Both should point to the same database.

### Generating a New Migration

When you make changes to your SQLAlchemy models (e.g., in `users/models.py` or `ai/models.py`), you need to generate a new migration script.

1. Ensure your virtual environment is activated.
2. Run the following command from the **project's root directory**:

     ```
     alembic revision -m "your_descriptive_migration_message" --autogenerate
     ```

     - Replace `"your_descriptive_migration_message"` with a short summary of the changes (e.g., "add_user_phone_number_column", "create_ai_tasks_table").
     - The `--autogenerate` flag attempts to detect changes in your models and create the migration script automatically.
     - A new script will be created in the `alembic/versions/` directory. **Always review this script** to ensure it accurately reflects the intended changes.

### Applying Migrations

To apply the generated migrations to your database (i.e., create or alter tables):

1. Ensure your virtual environment is activated.
2. Run the following command from the **project's root directory**:

     ```
     alembic upgrade head
     ```

     - `head` signifies that you want to upgrade to the latest migration version.
     - You can also target a specific migration revision ID.

### Downgrading Migrations (Reverting)

To revert migrations (use with caution), run from the **project's root directory**:

```
alembic downgrade -1         # Reverts the last applied migration
alembic downgrade base       # Reverts all migrations
alembic downgrade <revision_id> # Downgrades to a state before a specific revision
```

## Running the Application

Refer to the main project documentation or setup scripts for instructions on installing dependencies and running the FastAPI application server (e.g., using Uvicorn).

