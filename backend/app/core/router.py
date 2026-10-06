"""Core router aggregation.

Core is mounted as one router so that ``main.py`` stays a composition root:
adding a Core package means editing this file and the Alembic autogenerate
import, not the application factory (docs/architecture.md, section 64).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.activity.api import router as activity_router
from app.core.auth.api import router as auth_router
from app.core.organizations.api import router as organizations_router
from app.core.projects.api import router as projects_router
from app.core.settings.api import router as settings_router
from app.core.users.api import router as users_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(users_router)
router.include_router(organizations_router)
router.include_router(settings_router)
router.include_router(projects_router)
router.include_router(activity_router)
