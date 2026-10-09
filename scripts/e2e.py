"""End-to-end smoke check against a running stack.

Exercises the Phase 1 and Phase 2 acceptance flows (docs/architecture.md,
sections 50 and 65) through Caddy, exactly as a browser would: register, create
an organization and a project, invite a second user, then work with tasks and
comments and read the activity feed.

Every run uses fresh random identities. In single-organization mode (the
shipped default) the script additionally needs a clean database, because the
organization it sets up may only be created once: a reused installation is
detected right after registration and reported with the reset command.

    python scripts/e2e.py [base-url]
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
import uuid
from typing import Any

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost").rstrip("/")
PASSWORD = "sup3r-secret"


class CheckFailedError(Exception):
    pass


def call(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    """Return (status, decoded JSON).

    The payload is genuinely arbitrary JSON, so `Any` is the honest annotation
    here rather than an attempt to describe every response shape - the checks
    below are what actually pin the contract down.
    """
    request = urllib.request.Request(f"{BASE}{path}", method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None

    try:
        with urllib.request.urlopen(request, data, timeout=15) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return exc.code, {"raw": raw.decode(errors="replace")}


def check(label: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise CheckFailedError(f"{label}: expected {expected!r}, got {actual!r}")
    print(f"  ok  {label}")


def register(label: str) -> tuple[str, dict[str, str]]:
    handle = uuid.uuid4().hex[:8]
    status, body = call(
        "POST",
        "/api/v1/auth/register",
        body={
            "email": f"{label}-{handle}@example.com",
            "username": f"{label}_{handle}",
            "password": PASSWORD,
            "first_name": label.capitalize(),
        },
    )
    check(f"register {label}", status, 201)
    return str(body["access_token"]), {"email": str(body["user"]["email"]), "handle": handle}


def main() -> int:
    print(f"target: {BASE}")

    status, body = call("GET", "/health")
    check("liveness", status, 200)
    status, _ = call("GET", "/health/ready")
    check("readiness", status, 200)

    owner_token, owner = register("owner")
    handle = owner["handle"]

    status, body = call("GET", "/api/v1/auth/me", token=owner_token)
    check("session", status, 200)
    check("session identity", body["username"].startswith("owner_"), True)

    status, profile = call("GET", "/api/v1/users/me", token=owner_token)
    check("profile", status, 200)
    owner_id = str(profile["id"])
    if not profile["is_superuser"]:
        # Single-organization mode: only the portal administrator may set the
        # organization up, and on a reused installation that first account is
        # already taken - so the rest of the script has nothing to work with.
        raise CheckFailedError(
            "this account is not the portal administrator, so the installation "
            "already holds data. Single-organization mode needs a clean database: "
            "`docker compose down -v`, then `make up && make migrate` and re-run."
        )
    print("  ok  the first account is the portal administrator")

    # Slugs are unique platform-wide, so the name carries the run handle and the
    # script stays re-runnable against a stack that already holds data.
    organization_name = f"Acme {handle}"
    status, organization = call(
        "POST", "/api/v1/organizations", token=owner_token, body={"name": organization_name}
    )
    check("create organization", status, 201)
    organization_id = str(organization["id"])
    check("slug derived", organization["slug"], organization_name.lower().replace(" ", "-"))

    status, _project = call(
        "POST",
        "/api/v1/projects",
        token=owner_token,
        body={"organization_id": organization_id, "name": "Apollo"},
    )
    check("create project", status, 201)

    status, _ = call(
        "POST",
        "/api/v1/projects",
        token=owner_token,
        body={"organization_id": organization_id, "name": "Apollo"},
    )
    check("duplicate project rejected", status, 409)
    project_id = str(_project["id"])
    assignee_token, assignee = register("assignee")

    status, _ = call(
        "POST",
        f"/api/v1/organizations/{organization_id}/teams",
        token=owner_token,
        body={"name": "Backend"},
    )
    check("create team", status, 201)

    # A viewer proves the read-only role; a stranger proves the tenant boundary.
    # They are different people on purpose - a check that passes for an outsider
    # says nothing about the viewer role.
    viewer_token, viewer = register("viewer")
    status, member = call(
        "POST",
        f"/api/v1/organizations/{organization_id}/members",
        token=owner_token,
        body={"email": viewer["email"], "role": "viewer"},
    )
    check("invite by email", status, 201)
    check("invited role", member["role"], "viewer")
    viewer_id = str(member["user_id"])

    status, member = call(
        "POST",
        f"/api/v1/organizations/{organization_id}/members",
        token=owner_token,
        body={"email": assignee["email"], "role": "member"},
    )
    check("invite a member", status, 201)
    check("member role", member["role"], "member")
    assignee_id = str(member["user_id"])

    outsider_token, _ = register("stranger")
    status, _ = call(
        "POST",
        f"/api/v1/organizations/{organization_id}/teams",
        token=outsider_token,
        body={"name": "Sneaky"},
    )
    check("outsider blocked", status, 403)

    # --- Phase 2: tasks and comments -----------------------------------------
    status, task = call(
        "POST",
        f"/api/v1/projects/{project_id}/tasks?organization_id={organization_id}",
        token=owner_token,
        body={
            "title": "  Write the launch checklist  ",
            "description": "Everything that has to be true on day one.",
            "priority": "urgent",
        },
    )
    check("create task", status, 201)
    task_id = str(task["id"])
    check("title trimmed", task["title"], "Write the launch checklist")
    check("new task is todo", task["status"], "todo")
    check("no deadline yet", task["due_date"], None)

    status, _ = call(
        "POST",
        f"/api/v1/projects/{project_id}/tasks?organization_id={organization_id}",
        token=owner_token,
        body={"title": "Write it", "status": "done"},
    )
    check("unknown field in body rejected", status, 422)

    status, _ = call(
        "POST",
        f"/api/v1/projects/{project_id}/tasks?organization_id={organization_id}",
        token=viewer_token,
        body={"title": "Viewer tries"},
    )
    check("viewer cannot create a task", status, 403)

    status, updated = call(
        "PATCH",
        f"/api/v1/tasks/{task_id}?organization_id={organization_id}",
        token=owner_token,
        body={"assignee_id": assignee_id, "due_date": "2026-12-24"},
    )
    check("assign and set a deadline", status, 200)
    check("assignee stored", updated["assignee_id"], assignee_id)

    # Omitting a key must leave the value alone; sending null must clear it.
    status, untouched = call(
        "PATCH",
        f"/api/v1/tasks/{task_id}?organization_id={organization_id}",
        token=owner_token,
        body={"title": "Write the launch checklist v2"},
    )
    check("partial update", status, 200)
    # A bare date reads as midnight UTC (the deadline is an instant since
    # `4b110a7`), and a partial update must hand that same instant back.
    check("deadline survives a partial update", untouched["due_date"], "2026-12-24T00:00:00Z")

    status, cleared = call(
        "PATCH",
        f"/api/v1/tasks/{task_id}?organization_id={organization_id}",
        token=owner_token,
        body={"due_date": None},
    )
    check("null clears the deadline", status, 200)
    check("deadline cleared", cleared["due_date"], None)

    status, done = call(
        "PATCH",
        f"/api/v1/tasks/{task_id}?organization_id={organization_id}",
        token=owner_token,
        body={"status": "done"},
    )
    check("complete the task", status, 200)
    check("completion stamped", done["completed_at"] is not None, True)

    status, reopened = call(
        "PATCH",
        f"/api/v1/tasks/{task_id}?organization_id={organization_id}",
        token=owner_token,
        body={"status": "in_progress"},
    )
    check("reopen the task", status, 200)
    check("completion stamp cleared", reopened["completed_at"], None)

    for title, priority in (("Book the venue", "high"), ("Tidy the backlog", "low")):
        status, _ = call(
            "POST",
            f"/api/v1/projects/{project_id}/tasks?organization_id={organization_id}",
            token=owner_token,
            body={"title": title, "priority": priority},
        )
        check(f"create task {title!r}", status, 201)

    status, page = call(
        "GET",
        f"/api/v1/projects/{project_id}/tasks?organization_id={organization_id}&sort=priority"
        "&direction=asc",
        token=owner_token,
    )
    check("list tasks", status, 200)
    check(
        "priority ordered by meaning, not alphabetically",
        [item["priority"] for item in page["items"]],
        ["low", "high", "urgent"],
    )

    status, page = call(
        "GET",
        f"/api/v1/projects/{project_id}/tasks?organization_id={organization_id}&status=todo",
        token=owner_token,
    )
    check("filter by status", page["total"], 2)

    status, page = call(
        "GET",
        f"/api/v1/projects/{project_id}/tasks?organization_id={organization_id}&search=launch",
        token=owner_token,
    )
    check("search finds one task", page["total"], 1)

    status, page = call(
        "GET",
        f"/api/v1/projects/{project_id}/tasks?organization_id={organization_id}&assignee_id="
        f"{assignee_id}",
        token=assignee_token,
    )
    check("member sees own task", status, 200)
    check("my tasks", page["total"], 1)

    status, _ = call(
        "GET",
        f"/api/v1/projects/{project_id}/tasks?organization_id={organization_id}&sort=priorty",
        token=owner_token,
    )
    check("unknown sort field rejected", status, 422)

    status, comment = call(
        "POST",
        f"/api/v1/tasks/{task_id}/comments?organization_id={organization_id}",
        token=assignee_token,
        body={"content": "  I can take the checklist.  "},
    )
    check("member comments", status, 201)
    check("comment trimmed", comment["content"], "I can take the checklist.")

    status, page = call(
        "GET",
        f"/api/v1/tasks/{task_id}/comments?organization_id={organization_id}",
        token=viewer_token,
    )
    check("viewer reads comments", status, 200)
    check("one comment", page["total"], 1)

    status, _ = call(
        "POST",
        f"/api/v1/tasks/{task_id}/comments?organization_id={organization_id}",
        token=viewer_token,
        body={"content": "Not my place"},
    )
    check("viewer cannot comment", status, 403)

    status, _ = call(
        "DELETE",
        f"/api/v1/tasks/{task_id}/comments/{comment['id']}?organization_id={organization_id}",
        token=viewer_token,
    )
    check("viewer cannot delete somebody else's comment", status, 403)

    status, _ = call(
        "GET", f"/api/v1/tasks/{task_id}?organization_id={organization_id}", token=viewer_token
    )
    check("viewer reads a task", status, 200)

    status, _ = call(
        "DELETE",
        f"/api/v1/tasks/{task_id}/comments/{comment['id']}?organization_id={organization_id}",
        token=assignee_token,
    )
    check("author removes their own comment", status, 204)

    # 403, not 404: on a task the route authorizes before it loads, and telling a
    # non-member "no such task" would only make them hunt for valid ids.
    status, _ = call(
        "GET", f"/api/v1/tasks/{task_id}?organization_id={organization_id}", token=outsider_token
    )
    check("outsider refused a task", status, 403)

    status, _ = call(
        "GET",
        f"/api/v1/projects/{project_id}/tasks?organization_id={organization_id}",
        token=outsider_token,
    )
    check("outsider refused the project task list", status, 403)

    status, feed = call(
        "GET",
        f"/api/v1/activity?organization_id={organization_id}",
        token=owner_token,
    )
    check("read activity", status, 200)
    actions = [str(item["action"]) for item in feed["items"]]
    for expected in (
        "organization.created",
        "project.created",
        "team.created",
        "task.created",
        "task.assigned",
        "task.status_changed",
        "task.completed",
        "task.reopened",
        "comment.created",
    ):
        check(f"activity contains {expected}", expected in actions, True)
    check(
        "every row is tenant scoped",
        all(item["organization_id"] == organization_id for item in feed["items"]),
        True,
    )

    status, _ = call(
        "DELETE",
        f"/api/v1/tasks/{task_id}?organization_id={organization_id}",
        token=viewer_token,
    )
    check("viewer cannot delete a task", status, 403)

    status, _ = call(
        "DELETE",
        f"/api/v1/tasks/{task_id}?organization_id={organization_id}",
        token=assignee_token,
    )
    check("member cannot delete a task", status, 403)

    status, _ = call(
        "DELETE",
        f"/api/v1/tasks/{task_id}?organization_id={organization_id}",
        token=owner_token,
    )
    check("owner deletes a task", status, 204)

    status, _ = call(
        "GET", f"/api/v1/tasks/{task_id}?organization_id={organization_id}", token=owner_token
    )
    check("deleted task is gone", status, 404)

    status, page = call(
        "GET",
        f"/api/v1/tasks/{task_id}/comments?organization_id={organization_id}",
        token=owner_token,
    )
    check("comments went with the task", status, 404)

    status, settings = call(
        "GET", f"/api/v1/organizations/{organization_id}/settings", token=owner_token
    )
    check("read settings", status, 200)
    check("default locale", settings["values"]["locale"], "en")

    # --- tasks without a project --------------------------------------------
    # The inbox: a task that belongs to the organization and to no project. Without
    # this the first screen a new account meets is a project form.
    status, inbox_task = call(
        "POST",
        f"/api/v1/tasks?organization_id={organization_id}",
        token=owner_token,
        body={"title": "Call the vendor", "description": "Ask for a quote."},
    )
    check("create a task with no project", status, 201)
    check("no project yet", inbox_task["project_id"], None)
    inbox_task_id = str(inbox_task["id"])

    status, page = call(
        "GET",
        f"/api/v1/tasks?organization_id={organization_id}&unfiled=true",
        token=owner_token,
    )
    check("inbox lists the unfiled task", page["total"], 1)

    status, filed = call(
        "PATCH",
        f"/api/v1/tasks/{inbox_task_id}?organization_id={organization_id}",
        token=owner_token,
        body={"project_id": project_id},
    )
    check("file a task into a project", status, 200)
    check("project recorded", filed["project_id"], project_id)

    status, page = call(
        "GET",
        f"/api/v1/tasks?organization_id={organization_id}&unfiled=true",
        token=owner_token,
    )
    check("inbox is empty again", page["total"], 0)

    status, _ = call(
        "DELETE",
        f"/api/v1/tasks/{inbox_task_id}?organization_id={organization_id}",
        token=owner_token,
    )
    check("owner deletes the inbox task", status, 204)

    # --- a responsible person is not optional --------------------------------
    # A task with nobody on it is work that silently does not happen, so the
    # column refuses null and the API refuses to hand one over.
    status, owned = call(
        "POST",
        f"/api/v1/tasks?organization_id={organization_id}",
        token=assignee_token,
        body={"title": "Nobody named a responsible person"},
    )
    check("create a task naming nobody", status, 201)
    check("the creator becomes responsible", owned["assignee_id"], assignee_id)
    check("the reporter is remembered separately", owned["creator_id"], assignee_id)
    owned_id = str(owned["id"])

    status, _ = call(
        "PATCH",
        f"/api/v1/tasks/{owned_id}?organization_id={organization_id}",
        token=assignee_token,
        body={"assignee_id": None},
    )
    check("dropping the responsible person is refused", status, 422)

    status, handed = call(
        "PATCH",
        f"/api/v1/tasks/{owned_id}?organization_id={organization_id}",
        token=assignee_token,
        body={"assignee_id": owner_id},
    )
    check("handing a task over is allowed", status, 200)
    check("new responsible person recorded", handed["assignee_id"], owner_id)

    # --- a fourth status: deferred --------------------------------------------
    status, parked = call(
        "PATCH",
        f"/api/v1/tasks/{owned_id}?organization_id={organization_id}",
        token=owner_token,
        body={"status": "deferred"},
    )
    check("a task can be parked", status, 200)
    check("status recorded", parked["status"], "deferred")
    check("parked work is not finished", parked["completed_at"], None)

    status, page = call(
        "GET",
        f"/api/v1/projects/{project_id}/tasks?organization_id={organization_id}&status=deferred",
        token=owner_token,
    )
    check("filter by the parked status", status, 200)

    # --- co-assignees and watchers -------------------------------------------
    # The viewer is neither the reporter nor the responsible person of this task,
    # which is the only way somebody can be attached at all: adding either of them
    # again would be a second, contradictory answer to a question the task already
    # answers.
    status, _ = call(
        "POST",
        f"/api/v1/tasks/{owned_id}/participants?organization_id={organization_id}",
        token=owner_token,
        body={"user_id": assignee_id, "role": "co_assignee"},
    )
    check("the reporter cannot also be attached", status, 422)

    status, _ = call(
        "POST",
        f"/api/v1/tasks/{owned_id}/participants?organization_id={organization_id}",
        token=owner_token,
        body={"user_id": viewer_id, "role": "co_assignee"},
    )
    check("attach a co-assignee", status, 201)

    status, _ = call(
        "POST",
        f"/api/v1/tasks/{owned_id}/participants?organization_id={organization_id}",
        token=owner_token,
        body={"user_id": viewer_id, "role": "watcher"},
    )
    check("the same person can also watch", status, 201)

    status, listed = call(
        "GET",
        f"/api/v1/tasks/{owned_id}/participants?organization_id={organization_id}",
        token=owner_token,
    )
    check("both roles are listed", status, 200)
    check("two rows for one person", len(listed), 2)

    status, _ = call(
        "POST",
        f"/api/v1/tasks/{owned_id}/participants?organization_id={organization_id}",
        token=viewer_token,
        body={"user_id": assignee_id, "role": "watcher"},
    )
    check("a viewer cannot attach anybody", status, 403)

    status, _ = call(
        "DELETE",
        f"/api/v1/tasks/{owned_id}/participants/{viewer_id}"
        f"?organization_id={organization_id}&role=watcher",
        token=owner_token,
    )
    check("detach a watcher", status, 204)

    status, listed = call(
        "GET",
        f"/api/v1/tasks/{owned_id}/participants?organization_id={organization_id}",
        token=owner_token,
    )
    check("only the co-assignee is left", len(listed), 1)

    # --- planning -------------------------------------------------------------
    status, planned = call(
        "PATCH",
        f"/api/v1/tasks/{owned_id}?organization_id={organization_id}",
        token=owner_token,
        body={
            "planned_start": "2027-01-31T09:00:00Z",
            "planned_duration": 1,
            "duration_unit": "months",
        },
    )
    check("plan a window from a duration", status, 200)
    check("duration recorded", planned["planned_duration"], 1)
    # One month after 31 January is the end of February, not 3 March.
    check(
        "months are calendar aware",
        str(planned["planned_end"]).startswith("2027-02-28T09:00"),
        True,
    )

    status, _ = call(
        "PATCH",
        f"/api/v1/tasks/{owned_id}?organization_id={organization_id}",
        token=owner_token,
        body={"planned_start": "2027-01-10T09:00:00Z", "planned_end": "2027-01-01T09:00:00Z"},
    )
    check("an end before the start is refused", status, 422)

    status, _ = call(
        "DELETE",
        f"/api/v1/tasks/{owned_id}?organization_id={organization_id}",
        token=owner_token,
    )
    check("clean up the planning task", status, 204)

    # --- members and roles ----------------------------------------------------
    status, members = call(
        "GET", f"/api/v1/organizations/{organization_id}/members", token=owner_token
    )
    check("list members", status, 200)
    check("three members", len(members), 3)

    status, changed = call(
        "PATCH",
        f"/api/v1/organizations/{organization_id}/members/{viewer_id}",
        token=owner_token,
        body={"role": "member"},
    )
    check("change a member's role", status, 200)
    check("role applied", changed["role"], "member")

    status, _ = call(
        "PATCH",
        f"/api/v1/organizations/{organization_id}/members/{assignee_id}",
        token=viewer_token,
        body={"role": "owner"},
    )
    check("a member cannot promote themselves", status, 403)

    status, _ = call(
        "DELETE",
        f"/api/v1/organizations/{organization_id}/members/{viewer_id}",
        token=owner_token,
    )
    check("remove a member", status, 204)

    status, _ = call(
        "DELETE",
        f"/api/v1/organizations/{organization_id}/members/{owner_id}",
        token=owner_token,
    )
    check("the last owner cannot be removed", status, 422)

    # --- the single organization ---------------------------------------------
    # Whoever registers later cannot set the organization up: that is portal
    # configuration, and the account that already did it is the administrator.
    latecomer_token, _ = register("latecomer")
    status, _ = call(
        "POST",
        "/api/v1/organizations",
        token=latecomer_token,
        body={"name": f"Second {handle}"},
    )
    check("a plain account cannot create an organization", status, 403)

    status, _ = call(
        "POST",
        "/api/v1/organizations",
        token=owner_token,
        body={"name": f"Second {handle}"},
    )
    check("a second organization is refused", status, 409)

    # --- portal administration -----------------------------------------------
    # The user directory is the one cross-tenant read in the product, and since
    # `62e0737` it is open to every signed-in account: on a self-hosted
    # installation every tenant is the same deployment, so looking at the list is
    # a normal lookup. What stays superuser-only is granting rights over every
    # tenant - that is what the checks below pin down.
    status, _ = call("GET", "/api/v1/users?limit=200", token=owner_token)
    check("the bootstrap administrator sees the user directory", status, 200)

    status, _ = call("GET", "/api/v1/users?limit=200", token=assignee_token)
    check("a plain account sees the user directory", status, 200)

    status, _ = call("GET", "/api/v1/users?limit=200", token=outsider_token)
    check("a stranger sees the user directory", status, 200)

    # Nobody may hand the right to themselves; the holder may pass it on.
    status, outsider_profile = call("GET", "/api/v1/users/me", token=outsider_token)
    check("stranger profile", status, 200)
    outsider_id = str(outsider_profile["id"])

    status, _ = call(
        "PATCH",
        f"/api/v1/users/{outsider_id}/superuser",
        token=outsider_token,
        body={"is_superuser": True},
    )
    check("only an administrator may grant the right", status, 403)

    status, granted = call(
        "PATCH",
        f"/api/v1/users/{outsider_id}/superuser",
        token=owner_token,
        body={"is_superuser": True},
    )
    check("the bootstrap administrator grants the right", status, 200)
    check("the grant is applied", granted["is_superuser"], True)

    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CheckFailedError as exc:
        print(f"\nFAILED: {exc}")
        raise SystemExit(1) from exc
