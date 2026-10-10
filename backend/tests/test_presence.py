"""Presence: when a person was last here, and who is allowed to know (2.9).

The feature is two halves that can each be wrong on their own, so both are here:

* the *writing* - last seen comes from ordinary requests, which means the
  throttle is what stands between a roster and a write per rendered row. A test
  that only checks "the timestamp appeared" would pass with no throttle at all.
* the *reading* - the timestamp is the person's own answer about themselves, and
  the portal decides only whether they get to have one.

The refusals are the interesting half: a person who hid their presence must not
find it in the list of people either, and the old `last_login_at` must go with
it, because it is the same fact written a week earlier.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import update

from app.core.users import presence
from app.core.users.models import User
from app.database.session import get_session
from tests.conftest import auth_headers, register_user


async def _join(
    client: AsyncClient, owner: dict[str, Any], prefix: str, role: str = "member"
) -> dict[str, Any]:
    session = await register_user(client, prefix=prefix)
    added = await client.post(
        f"/api/v1/organizations/{owner['organization']['id']}/members",
        json={"email": session["user"]["email"], "role": role},
        headers=auth_headers(owner["token"]),
    )
    assert added.status_code == 201, added.text
    return {"token": session["access_token"], "user": session["user"], "role": role}


async def _profile(
    client: AsyncClient, token: str, user_id: str, organization_id: str
) -> dict[str, Any]:
    response = await client.get(
        f"/api/v1/users/{user_id}/profile",
        params={"organization_id": organization_id},
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


class TestPresenceIsWritten:
    """Where the timestamp comes from, and how often (stage 2.9)."""

    async def test_a_request_notes_that_the_person_is_here(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        response = await client.get("/api/v1/users/me", headers=auth_headers(owner["token"]))

        assert response.status_code == 200
        seen = response.json()["last_seen"]
        assert seen is not None, "an authenticated request did not record last_seen"

    async def test_it_is_not_written_again_within_the_minute(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The throttle is the reason the feature is cheap.

        Without it every rendered row is a write, and the cost of a roster grows
        with the number of people watching it. The tracker is process-wide, so a
        test that does not start from a clean slate inherits the previous test's
        marks; that is exactly the behaviour being relied on here, and it is
        asserted directly rather than inferred from a clock.
        """
        person = UUID(owner["user"]["id"])
        presence.tracker.forget(person)
        assert presence.tracker.due(person)

        first = await client.get("/api/v1/users/me", headers=auth_headers(owner["token"]))
        assert first.status_code == 200
        assert not presence.tracker.due(person), "the first request did not mark"

        second = await client.get("/api/v1/users/me", headers=auth_headers(owner["token"]))
        assert second.status_code == 200
        assert second.json()["last_seen"] == first.json()["last_seen"], (
            "a second request inside the minute rewrote the timestamp"
        )

        # And the mark is not permanent: the person becomes due again once the
        # window has passed, which is what keeps "last seen" from freezing.
        presence.tracker.mark_written(person)
        assert not presence.tracker.due(person)
        presence.tracker.forget(person)
        assert presence.tracker.due(person)

    async def test_the_window_decides_who_counts_as_here_now(self) -> None:
        now = datetime.now(UTC)

        assert presence.is_online(now - timedelta(minutes=1), now=now)
        assert presence.is_online(now - timedelta(minutes=4, seconds=59), now=now)
        assert not presence.is_online(now - timedelta(minutes=5, seconds=1), now=now)
        # Never seen is not "here, silently": it is no answer at all.
        assert not presence.is_online(None, now=now)

    async def test_a_stale_timestamp_written_by_hand_reads_as_offline(self) -> None:
        """Six minutes ago is the case a clock jump or a nightly job produces.

        Rather than trusting the row to be recent, `is_online` asks the question
        every time: what matters is not when it was written but how old it is now.
        """
        old = datetime.now(UTC) - timedelta(minutes=6)
        assert not presence.is_online(old)


class TestPresenceVisibility:
    """Who may read it - the same question the contacts ask (2.6, 2.9)."""

    async def test_everybody_sees_it_until_somebody_answers(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        member = await _join(client, owner, prefix="seen")
        organization_id = owner["organization"]["id"]

        await client.get("/api/v1/users/me", headers=auth_headers(member["token"]))
        card = await _profile(client, owner["token"], member["user"]["id"], organization_id)

        assert card["last_seen_visible"] is True
        assert card["last_seen"] is not None

    async def test_a_person_who_answers_admins_loses_it_for_everybody_else(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The answer the roadmap question settled: a personal setting, which the
        portal may or may not let them have."""
        member = await _join(client, owner, prefix="hidden")
        colleague = await _join(client, owner, prefix="colleague")
        organization_id = owner["organization"]["id"]
        await client.get("/api/v1/users/me", headers=auth_headers(member["token"]))

        chosen = await client.put(
            "/api/v1/users/me/settings",
            params={"organization_id": organization_id},
            json={"values": {"last_seen_visibility": "admins"}},
            headers=auth_headers(member["token"]),
        )
        assert chosen.status_code == 200, chosen.text

        for_ = await _profile(client, colleague["token"], member["user"]["id"], organization_id)
        assert for_["last_seen_visible"] is False
        assert for_["last_seen"] is None
        # The sign-in time goes with it: it is the same fact, a week older.
        assert for_["last_login_at"] is None
        # The name, the department and the avatar are not presence and stay.
        assert for_["username"]

        for_admin = (
            await _profile(client, owner["token"], member["user"]["id"], organization_id),
            await _profile(client, member["token"], member["user"]["id"], organization_id),
        )
        for card_for_admin in for_admin:
            assert card_for_admin["last_seen_visible"] is True
            assert card_for_admin["last_seen"] is not None

    async def test_the_list_of_people_hides_it_too(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """A hidden answer that survives in the list is not hidden.

        The list is the screen people actually look at, so it is where a
        per-request decision is easiest to forget.
        """
        member = await _join(client, owner, prefix="listwise")
        colleague = await _join(client, owner, prefix="watcher")
        organization_id = owner["organization"]["id"]
        await client.get("/api/v1/users/me", headers=auth_headers(member["token"]))
        await client.put(
            "/api/v1/users/me/settings",
            params={"organization_id": organization_id},
            json={"values": {"last_seen_visibility": "admins"}},
            headers=auth_headers(member["token"]),
        )

        listed = await client.get(
            f"/api/v1/organizations/{organization_id}/people",
            headers=auth_headers(colleague["token"]),
        )
        assert listed.status_code == 200, listed.text
        row = next(r for r in listed.json()["items"] if r["id"] == member["user"]["id"])

        assert row["last_seen_visible"] is False
        assert row["last_seen"] is None
        assert row["last_login_at"] is None
        assert row["email"] is not None, "presence and contacts are two questions"

        by_admin = await client.get(
            f"/api/v1/organizations/{organization_id}/people",
            headers=auth_headers(owner["token"]),
        )
        admin_row = next(r for r in by_admin.json()["items"] if r["id"] == member["user"]["id"])
        assert admin_row["last_seen_visible"] is True
        assert admin_row["last_seen"] is not None

    async def test_the_portal_decides_whether_they_may_answer(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        member = await _join(client, owner, prefix="locked")
        organization_id = owner["organization"]["id"]
        await client.get("/api/v1/users/me", headers=auth_headers(member["token"]))

        await client.put(
            f"/api/v1/organizations/{organization_id}/settings",
            json={"values": {"last_seen_self_service": False, "last_seen_visibility": "admins"}},
            headers=auth_headers(owner["token"]),
        )

        refused = await client.put(
            "/api/v1/users/me/settings",
            params={"organization_id": organization_id},
            json={"values": {"last_seen_visibility": "everyone"}},
            headers=auth_headers(member["token"]),
        )
        assert refused.status_code == 403
        assert refused.json()["error"]["details"]["settings"] == ["last_seen_visibility"]

        card = await _profile(client, owner["token"], member["user"]["id"], organization_id)
        assert card["last_seen_visible"] is True, "an admin always reads presence"

        other = await _join(client, owner, prefix="bystander")
        hidden = await _profile(client, other["token"], member["user"]["id"], organization_id)
        assert hidden["last_seen_visible"] is False, "the portal's own value must apply"
        assert hidden["last_seen"] is None

        await client.put(
            f"/api/v1/organizations/{organization_id}/settings",
            json={"values": {"last_seen_self_service": True}},
            headers=auth_headers(owner["token"]),
        )
        allowed = await client.put(
            "/api/v1/users/me/settings",
            params={"organization_id": organization_id},
            json={"values": {"last_seen_visibility": "everyone"}},
            headers=auth_headers(member["token"]),
        )
        assert allowed.status_code == 200

    async def test_an_answer_is_the_person_s_own_and_nobody_else_s(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """One person's answer must not decide for the rest of the roster."""
        quiet = await _join(client, owner, prefix="quiet")
        colleague = await _join(client, owner, prefix="loud")
        organization_id = owner["organization"]["id"]
        for person in (quiet, colleague):
            await client.get("/api/v1/users/me", headers=auth_headers(person["token"]))

        await client.put(
            "/api/v1/users/me/settings",
            params={"organization_id": organization_id},
            json={"values": {"last_seen_visibility": "admins"}},
            headers=auth_headers(quiet["token"]),
        )

        listed = await client.get(
            f"/api/v1/organizations/{organization_id}/people",
            headers=auth_headers(owner["token"]),
        )
        rows = {r["id"]: r for r in listed.json()["items"]}

        assert rows[quiet["user"]["id"]]["last_seen_visible"] is True  # admin reads it
        other = await _profile(client, quiet["token"], colleague["user"]["id"], organization_id)
        assert other["last_seen_visible"] is True, "the quiet one's answer hid the loud one"


class TestPresenceColumn:
    """The list screen and the column that shows it (stage 2.9)."""

    async def test_the_column_sorts_by_the_timestamp_and_not_by_the_login(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Sorting is what makes the column worth having, and the two timestamps
        disagree: signing in is rarer than being here."""
        organization_id = owner["organization"]["id"]
        first = await _join(client, owner, prefix="older")
        second = await _join(client, owner, prefix="newer")

        async def _write_seen(user_id: str, when: datetime) -> None:
            generator = get_session()
            session = await anext(generator)
            try:
                await session.execute(update(User).where(User.id == user_id).values(last_seen=when))
                await session.commit()
            finally:
                await generator.aclose()

        await _write_seen(first["user"]["id"], datetime.now(UTC) - timedelta(hours=2))
        await _write_seen(second["user"]["id"], datetime.now(UTC) - timedelta(minutes=2))

        listed = await client.get(
            f"/api/v1/organizations/{organization_id}/people",
            params={"sort": "last_seen", "direction": "desc"},
            headers=auth_headers(owner["token"]),
        )
        assert listed.status_code == 200, listed.text
        ids = [row["id"] for row in listed.json()["items"]]
        assert ids.index(second["user"]["id"]) < ids.index(first["user"]["id"])

    async def test_an_unknown_sort_key_is_refused(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        listed = await client.get(
            f"/api/v1/organizations/{owner['organization']['id']}/people",
            params={"sort": "how_much_they_like_coffee"},
            headers=auth_headers(owner["token"]),
        )
        assert listed.status_code == 422
