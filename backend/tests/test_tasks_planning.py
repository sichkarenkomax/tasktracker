"""Co-assignees, watchers, planning and the fourth status.

Everything here is a Phase 3 addition (docs/architecture.md, section 52) that
changed an existing rule rather than adding a parallel one: a task now always has
a responsible person, work can be parked as "deferred", and a task can carry a
planned window with a duration in any of five units.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from httpx import AsyncClient

from tests.conftest import auth_headers


async def _project(client: AsyncClient, owner: dict[str, Any], name: str = "Apollo") -> str:
    response = await client.post(
        "/api/v1/projects",
        json={"organization_id": owner["organization"]["id"], "name": name},
        headers=auth_headers(owner["token"]),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _task(client: AsyncClient, owner: dict[str, Any], **extra: Any) -> dict[str, Any]:
    project_id = await _project(client, owner)
    response = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        params={"organization_id": owner["organization"]["id"]},
        json={"title": "Prepare report", **extra},
        headers=auth_headers(owner["token"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _add_member(
    client: AsyncClient, owner: dict[str, Any], invitee: dict[str, Any], role: str = "member"
) -> None:
    response = await client.post(
        f"/api/v1/organizations/{owner['organization']['id']}/members",
        json={"email": invitee["user"]["email"], "role": role},
        headers=auth_headers(owner["token"]),
    )
    assert response.status_code == 201, response.text


class TestResponsibleIsMandatory:
    async def test_unassigning_is_refused(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        """A task with nobody on it is work that silently does not happen."""
        task = await _task(client, owner)

        response = await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": owner["organization"]["id"]},
            json={"assignee_id": None},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 422

    async def test_handing_over_is_allowed(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await _add_member(client, owner, outsider)
        task = await _task(client, owner)

        response = await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": owner["organization"]["id"]},
            json={"assignee_id": outsider["user"]["id"]},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200, response.text
        assert response.json()["assignee_id"] == outsider["user"]["id"]


class TestDeferred:
    async def test_a_task_can_be_parked(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        task = await _task(client, owner)

        response = await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": owner["organization"]["id"]},
            json={"status": "deferred"},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "deferred"

    async def test_deferred_is_not_completed(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Parked work is still open, so it is not stamped as finished."""
        task = await _task(client, owner)

        response = await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": owner["organization"]["id"]},
            json={"status": "deferred"},
            headers=auth_headers(owner["token"]),
        )

        assert response.json()["completed_at"] is None

    async def test_a_deferred_task_can_still_be_overdue(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        from datetime import date, timedelta

        task = await _task(client, owner, due_date=str(date.today() - timedelta(days=2)))
        await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": owner["organization"]["id"]},
            json={"status": "deferred"},
            headers=auth_headers(owner["token"]),
        )

        response = await client.get(
            "/api/v1/tasks",
            params={"organization_id": owner["organization"]["id"], "overdue": True},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200
        assert [item["id"] for item in response.json()["items"]] == [task["id"]]


class TestParticipants:
    async def test_attach_a_co_assignee(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await _add_member(client, owner, outsider)
        task = await _task(client, owner)

        response = await client.post(
            f"/api/v1/tasks/{task['id']}/participants",
            params={"organization_id": owner["organization"]["id"]},
            json={"user_id": outsider["user"]["id"], "role": "co_assignee"},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 201, response.text
        assert response.json()["role"] == "co_assignee"

    async def test_a_watcher_is_not_a_co_assignee(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        """The two roles are separate rows, so somebody can be both."""
        await _add_member(client, owner, outsider)
        task = await _task(client, owner)
        organization_id = owner["organization"]["id"]
        headers = auth_headers(owner["token"])

        for role in ("watcher", "co_assignee"):
            response = await client.post(
                f"/api/v1/tasks/{task['id']}/participants",
                params={"organization_id": organization_id},
                json={"user_id": outsider["user"]["id"], "role": role},
                headers=headers,
            )
            assert response.status_code == 201, response.text

        listed = await client.get(
            f"/api/v1/tasks/{task['id']}/participants",
            params={"organization_id": organization_id},
            headers=headers,
        )
        assert listed.status_code == 200
        assert len(listed.json()) == 2

    async def test_attaching_the_same_role_twice_is_harmless(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        """Adding somebody twice returns the row that is already there.

        The unique index is what makes a second insert impossible; the service
        checks first so the caller sees a success rather than a constraint error.
        """
        await _add_member(client, owner, outsider)
        task = await _task(client, owner)
        organization_id = owner["organization"]["id"]
        headers = auth_headers(owner["token"])
        body = {"user_id": outsider["user"]["id"], "role": "watcher"}

        first = await client.post(
            f"/api/v1/tasks/{task['id']}/participants",
            params={"organization_id": organization_id},
            json=body,
            headers=headers,
        )
        second = await client.post(
            f"/api/v1/tasks/{task['id']}/participants",
            params={"organization_id": organization_id},
            json=body,
            headers=headers,
        )
        listed = await client.get(
            f"/api/v1/tasks/{task['id']}/participants",
            params={"organization_id": organization_id},
            headers=headers,
        )

        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json() == second.json()
        assert len(listed.json()) == 1

    async def test_the_reporter_cannot_also_be_attached(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Attaching the creator as a watcher would be a second, contradictory
        answer to "who reported this"."""
        task = await _task(client, owner)

        response = await client.post(
            f"/api/v1/tasks/{task['id']}/participants",
            params={"organization_id": owner["organization"]["id"]},
            json={"user_id": owner["user"]["id"], "role": "watcher"},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 422

    async def test_somebody_outside_the_organization_is_refused(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        task = await _task(client, owner)

        response = await client.post(
            f"/api/v1/tasks/{task['id']}/participants",
            params={"organization_id": owner["organization"]["id"]},
            json={"user_id": outsider["user"]["id"], "role": "watcher"},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 422

    async def test_detaching(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await _add_member(client, owner, outsider)
        task = await _task(client, owner)
        organization_id = owner["organization"]["id"]
        headers = auth_headers(owner["token"])
        await client.post(
            f"/api/v1/tasks/{task['id']}/participants",
            params={"organization_id": organization_id},
            json={"user_id": outsider["user"]["id"], "role": "watcher"},
            headers=headers,
        )

        removed = await client.delete(
            f"/api/v1/tasks/{task['id']}/participants/{outsider['user']['id']}",
            params={"organization_id": organization_id, "role": "watcher"},
            headers=headers,
        )
        listed = await client.get(
            f"/api/v1/tasks/{task['id']}/participants",
            params={"organization_id": organization_id},
            headers=headers,
        )

        assert removed.status_code == 204
        assert listed.json() == []

    async def test_a_viewer_cannot_attach_anybody(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await _add_member(client, owner, outsider, role="viewer")
        task = await _task(client, owner)

        response = await client.post(
            f"/api/v1/tasks/{task['id']}/participants",
            params={"organization_id": owner["organization"]["id"]},
            json={"user_id": outsider["user"]["id"], "role": "watcher"},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403


class TestPlanning:
    async def test_a_window_is_stored_verbatim(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        task = await _task(
            client,
            owner,
            planned_start="2026-11-02T09:00:00Z",
            planned_end="2026-11-06T17:00:00Z",
        )

        assert task["planned_start"] is not None
        assert task["planned_end"] is not None
        assert task["planned_end"] > task["planned_start"]

    async def test_a_duration_computes_the_end(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        task = await _task(
            client,
            owner,
            planned_start="2026-11-02T09:00:00Z",
            planned_duration=3,
            duration_unit="days",
        )

        assert task["planned_duration"] == 3
        assert task["planned_end"] is not None
        # Three days after Monday 2 November is Thursday 5 November.
        assert task["planned_end"].startswith("2026-11-05T09:00")

    async def test_months_are_calendar_aware(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """One month after 31 January is the end of February, not 3 March."""
        task = await _task(
            client,
            owner,
            planned_start="2027-01-31T09:00:00Z",
            planned_duration=1,
            duration_unit="months",
        )

        assert task["planned_end"].startswith("2027-02-28T09:00")

    async def test_minutes_are_available(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        task = await _task(
            client,
            owner,
            planned_start="2026-11-02T09:00:00Z",
            planned_duration=45,
            duration_unit="minutes",
        )

        assert task["planned_end"].startswith("2026-11-02T09:45")

    async def test_weeks_are_available(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        task = await _task(
            client,
            owner,
            planned_start="2026-11-02T09:00:00Z",
            planned_duration=2,
            duration_unit="weeks",
        )

        assert task["planned_end"].startswith("2026-11-16T09:00")

    async def test_a_duration_needs_a_start(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        response = await client.post(
            "/api/v1/tasks",
            params={"organization_id": owner["organization"]["id"]},
            json={"title": "No anchor", "planned_duration": 3, "duration_unit": "days"},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 422

    async def test_an_end_before_the_start_is_refused(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        response = await client.post(
            "/api/v1/tasks",
            params={"organization_id": owner["organization"]["id"]},
            json={
                "title": "Backwards",
                "planned_start": "2026-11-10T09:00:00Z",
                "planned_end": "2026-11-01T09:00:00Z",
            },
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 422

    async def test_a_contradictory_end_is_refused(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Silently preferring one of two disagreeing inputs hides a client bug."""
        response = await client.post(
            "/api/v1/tasks",
            params={"organization_id": owner["organization"]["id"]},
            json={
                "title": "Disagrees with itself",
                "planned_start": "2026-11-02T09:00:00Z",
                "planned_end": "2026-11-20T09:00:00Z",
                "planned_duration": 3,
                "duration_unit": "days",
            },
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 422

    async def test_a_negative_duration_is_refused(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        response = await client.post(
            "/api/v1/tasks",
            params={"organization_id": owner["organization"]["id"]},
            json={
                "title": "Back to the past",
                "planned_start": datetime.now(UTC).isoformat(),
                "planned_duration": -1,
            },
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 422

    async def test_moving_the_duration_recomputes_the_end(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        task = await _task(
            client,
            owner,
            planned_start="2026-11-02T09:00:00Z",
            planned_duration=3,
            duration_unit="days",
        )
        organization_id = owner["organization"]["id"]

        response = await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": organization_id},
            json={"planned_duration": 1, "duration_unit": "weeks"},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200, response.text
        assert response.json()["planned_end"].startswith("2026-11-09T09:00")

    async def test_clearing_the_plan(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        task = await _task(
            client,
            owner,
            planned_start="2026-11-02T09:00:00Z",
            planned_duration=3,
            duration_unit="days",
        )

        response = await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": owner["organization"]["id"]},
            json={"planned_start": None, "planned_end": None, "planned_duration": None},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["planned_start"] is None
        assert body["planned_end"] is None
        assert body["planned_duration"] is None

    async def test_omitting_the_plan_leaves_it_alone(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        task = await _task(
            client,
            owner,
            planned_start="2026-11-02T09:00:00Z",
            planned_duration=3,
            duration_unit="days",
        )

        response = await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": owner["organization"]["id"]},
            json={"title": "Renamed only"},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200
        assert response.json()["planned_end"] is not None
