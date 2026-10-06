"""Module Registry: discovery, dependency resolution and registration.

A module is a logically isolated unit of functionality that ships inside the
same application (docs/architecture.md, sections 22-24). On Phase 0 modules
are physical packages under ``app/modules`` - there is no marketplace, no ZIP
upload and no dependency resolver.
"""

from app.core.modules.manager import (
    ModuleDependencyError,
    ModuleError,
    ModuleManager,
    ModuleState,
    RegisteredModule,
)
from app.core.modules.manifest import MODULE_ID_PATTERN, ModuleManifest
from app.core.modules.registry import (
    ModuleBundle,
    discover_modules,
    import_module_packages,
)

__all__ = [
    "MODULE_ID_PATTERN",
    "ModuleBundle",
    "ModuleDependencyError",
    "ModuleError",
    "ModuleManager",
    "ModuleManifest",
    "ModuleState",
    "RegisteredModule",
    "discover_modules",
    "import_module_packages",
]
