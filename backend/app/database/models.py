"""Import side effects: register every Core and module model with Base.metadata.

Alembic autogenerate compares ``Base.metadata`` against the live schema, so a
model that nobody imports is invisible to it (docs/architecture.md, 46). The test
suite truncates ``Base.metadata.tables`` for the same reason.

Module models are imported here rather than in each module's ``__init__``:
``import_module_packages()`` in ``alembic/env.py`` imports the module *package*,
which does not import ``models``, so a module that only declared its models would
be missing from autogenerate.
"""

from __future__ import annotations

from app.core.activity import models as activity_models
from app.core.organizations import models as organization_models
from app.core.projects import models as project_models
from app.core.settings import models as settings_models
from app.core.users import models as user_models
from app.modules.tasks import models as task_models

__all__ = [
    "activity_models",
    "organization_models",
    "project_models",
    "settings_models",
    "task_models",
    "user_models",
]
