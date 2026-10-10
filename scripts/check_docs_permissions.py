"""Checks the documented permissions against the ones the code actually has.

The table in README.md and the catalogue in docs/architecture.md are copies, and
copies drift: a permission added to the registry in code leaves both documents
quietly incomplete, and the first person to notice is the one relying on it.
This script reports the difference and changes nothing.

    python scripts/check_docs_permissions.py

Exit code is 1 when a permission from the code is undocumented, so it can be
wired into the same checks as the rest.
"""

import pathlib
import re
import sys

root = pathlib.Path(__file__).resolve().parent.parent
roles = (root / "backend/app/core/permissions/roles.py").read_text(encoding="utf-8")
registry = (root / "backend/app/core/permissions/registry.py").read_text(encoding="utf-8")
tasks = (root / "backend/app/modules/tasks/permissions.py").read_text(encoding="utf-8")
readme = (root / "README.md").read_text(encoding="utf-8")
arch = (root / "docs/architecture.md").read_text(encoding="utf-8")

code = set(re.findall(r'"([a-z]+\.[a-z_]+)"', roles))
code |= set(re.findall(r'"([a-z]+\.[a-z_]+)"', registry))
code |= set(re.findall(r'=\s*"([a-z]+\.[a-z_]+)"', tasks))

docs = set(re.findall(r"[`]([a-z]+\.[a-z_]+)[`]", readme + arch))

print("permissions in code:", len(code))
print("documented:", len(code & docs))
missing = sorted(code - docs)
if missing:
    print("undocumented:", ", ".join(missing))
    sys.exit(1)
print("no undocumented permissions")
