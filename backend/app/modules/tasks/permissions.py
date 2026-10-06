"""Permissions declared by the Tasks module.

The strings live here so that a check never spells them out by hand, but the
mapping from role to permission stays in Core (``app.core.permissions.roles``).
Core knowing *which strings exist* is not the same as Core depending on the
module, and that is what lets the module be disabled without touching the
platform (docs/architecture.md, sections 25 and 64).

Roles come later - organization, team, project and custom roles are Phase 3+
(section 25) - so for now the distinction between ``task.update`` and
``task.complete`` has no observable effect. It is still checked, so that adding
a role which may edit tasks but not close them stays a one-line change.
"""

from __future__ import annotations

from typing import Final

VIEW: Final = "task.view"
CREATE: Final = "task.create"
UPDATE: Final = "task.update"
DELETE: Final = "task.delete"
ASSIGN: Final = "task.assign"
COMPLETE: Final = "task.complete"
COMMENT_CREATE: Final = "comment.create"
COMMENT_DELETE: Final = "comment.delete"

ALL: Final[frozenset[str]] = frozenset(
    {
        VIEW,
        CREATE,
        UPDATE,
        DELETE,
        ASSIGN,
        COMPLETE,
        COMMENT_CREATE,
        COMMENT_DELETE,
    }
)
"""Everything the module checks for.

The manifest advertises the same set. Keeping one authoritative list means a
permission can never be enforced without being declared, and Core can tell an
undeclared permission from a typo.
"""


def missing_from(granted: frozenset[str]) -> frozenset[str]:
    """Permissions a role lacks - used by the manifest consistency test."""
    return ALL - granted
