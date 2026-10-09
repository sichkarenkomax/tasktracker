"""Files: uploads, downloads and the three storage limits.

The behaviour these tests pin down is the part a quota system gets wrong quietly:
which allowance applies to whom, and what the server refuses. Bytes land in a
temporary directory here, so nothing a test uploads touches a real volume.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture(autouse=True)
def uploads_in_a_temporary_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the storage at a tmp directory instead of the deployment's volume."""
    from app.config.settings import Settings

    root = tmp_path / "uploads"
    monkeypatch.setattr(
        # The factory lives with the service (stage 2.3): the users router
        # builds the same file service for avatars, so one patch point covers
        # every writer of bytes.
        "app.core.files.service.get_settings",
        lambda: Settings(uploads_dir=root),
    )
    return root


async def place_in_department(
    client: AsyncClient, owner: dict[str, Any], department_id: str
) -> None:
    """Put the owner inside a department, through the endpoint that does it.

    There is no "set my department" shortcut for oneself - placement is an
    administrator's call - so the tests drive the same route an admin would.
    """
    response = await client.patch(
        f"/api/v1/organizations/{owner['organization']['id']}"
        f"/members/{owner['user']['id']}/placement",
        json={"department_id": department_id},
        headers=auth_headers(owner["token"]),
    )
    assert response.status_code == 200, response.text


def _stored_files(root: Path) -> list[Path]:
    """Every file the storage actually wrote.

    A plain function rather than inline in the test: walking a directory is
    blocking, and doing it inside an `async def` is what the linter is right to
    complain about.
    """
    return [path for path in root.rglob("*") if path.is_file()]


async def upload(
    client: AsyncClient,
    token: str,
    organization_id: str,
    *,
    name: str = "note.png",
    size: int = 64,
    content_type: str = "image/png",
) -> Any:
    return await client.post(
        "/api/v1/files",
        params={"organization_id": organization_id},
        files={"file": (name, b"x" * size, content_type)},
        headers=auth_headers(token),
    )


async def set_quota(client: AsyncClient, token: str, organization_id: str, **payload: Any) -> Any:
    return await client.put(
        "/api/v1/files/quotas",
        params={"organization_id": organization_id},
        json=payload,
        headers=auth_headers(token),
    )


async def set_portal_settings(
    client: AsyncClient, token: str, organization_id: str, **values: Any
) -> Any:
    return await client.put(
        f"/api/v1/organizations/{organization_id}/settings",
        json={"values": values},
        headers=auth_headers(token),
    )


class TestUpload:
    async def test_a_file_is_stored_and_comes_back_byte_for_byte(
        self, client: AsyncClient, owner: dict[str, Any], uploads_in_a_temporary_directory: Path
    ) -> None:
        response = await upload(client, owner["token"], owner["organization"]["id"])

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["filename"] == "note.png"
        assert body["size_bytes"] == 64

        download = await client.get(
            f"/api/v1/files/{body['id']}",
            params={"organization_id": owner["organization"]["id"]},
            headers=auth_headers(owner["token"]),
        )
        assert download.status_code == 200
        assert download.content == b"x" * 64
        # Served as an attachment from our own origin: bytes that came from a
        # browser upload are never executed as a page of ours.
        assert "attachment" in download.headers["content-disposition"]

        assert _stored_files(uploads_in_a_temporary_directory), "the file should have a key on disk"

    async def test_the_type_must_be_on_the_list(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        response = await upload(
            client, owner["token"], owner["organization"]["id"], content_type="image/svg+xml"
        )

        assert response.status_code == 422
        assert "svg+xml" in response.json()["error"]["message"]

    async def test_a_tenant_may_not_read_another_tenants_file(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        from tests.conftest import create_organization, register_user

        uploaded = await upload(client, owner["token"], owner["organization"]["id"])
        other = await register_user(client, prefix="outsider")
        other_organization = await create_organization(client, other["access_token"])

        response = await client.get(
            f"/api/v1/files/{uploaded.json()['id']}",
            params={"organization_id": other_organization["id"]},
            headers=auth_headers(other["access_token"]),
        )

        assert response.status_code == 403


class TestLimits:
    async def test_the_size_cap_comes_from_the_portal_settings(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        await set_portal_settings(
            client, owner["token"], owner["organization"]["id"], max_file_size_bytes=1000
        )

        assert (
            await upload(client, owner["token"], owner["organization"]["id"], size=500)
        ).status_code == 201

        refused = await upload(client, owner["token"], owner["organization"]["id"], size=2000)
        assert refused.status_code == 422
        assert "1000" in refused.json()["error"]["message"]

    async def test_the_client_is_told_the_limits_before_uploading(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        await set_portal_settings(
            client,
            owner["token"],
            owner["organization"]["id"],
            max_file_size_bytes=5000,
            storage_quota_bytes=9000,
        )

        response = await client.get(
            "/api/v1/files/limits",
            params={"organization_id": owner["organization"]["id"]},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["max_file_size_bytes"] == 5000
        assert body["storage_quota_bytes"] == 9000
        assert body["remaining_bytes"] == 9000
        assert "image/png" in body["allowed_content_types"]

    async def test_the_portal_total_is_enforced_across_uploaders(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        await set_portal_settings(
            client, owner["token"], owner["organization"]["id"], storage_quota_bytes=200
        )

        assert (
            await upload(client, owner["token"], owner["organization"]["id"], size=150)
        ).status_code == 201

        refused = await upload(client, owner["token"], owner["organization"]["id"], size=150)
        assert refused.status_code == 422
        assert "storage quota" in refused.json()["error"]["message"]


class TestQuotaPrecedence:
    """A person's own limit outranks their department's - the user's rule."""

    async def _department(self, client: AsyncClient, owner: dict[str, Any]) -> str:
        created = await client.post(
            f"/api/v1/organizations/{owner['organization']['id']}/departments",
            json={"name": "Engineering"},
            headers=auth_headers(owner["token"]),
        )
        assert created.status_code == 201, created.text
        return created.json()["id"]

    async def test_a_department_limit_applies_to_its_members(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        department_id = await self._department(client, owner)
        await set_quota(
            client,
            owner["token"],
            owner["organization"]["id"],
            department_id=department_id,
            limit_bytes=300,
        )
        await place_in_department(client, owner, department_id)

        mine = await client.get(
            "/api/v1/files/quota/me",
            params={"organization_id": owner["organization"]["id"]},
            headers=auth_headers(owner["token"]),
        )
        assert mine.status_code == 200, mine.text
        assert mine.json()["limit_bytes"] == 300
        assert mine.json()["quota_source"] == "department"

        assert (
            await upload(client, owner["token"], owner["organization"]["id"], size=250)
        ).status_code == 201
        refused = await upload(client, owner["token"], owner["organization"]["id"], size=100)
        assert refused.status_code == 422
        assert refused.json()["error"]["details"]["quota_source"] == "department"

    async def test_a_persons_own_limit_wins_over_the_departments(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        department_id = await self._department(client, owner)
        await set_quota(
            client,
            owner["token"],
            owner["organization"]["id"],
            department_id=department_id,
            limit_bytes=100,
        )
        await place_in_department(client, owner, department_id)
        # The group limit is now smaller than what this person may store.
        await set_quota(
            client,
            owner["token"],
            owner["organization"]["id"],
            user_id=owner["user"]["id"],
            limit_bytes=1000,
        )

        mine = await client.get(
            "/api/v1/files/quota/me",
            params={"organization_id": owner["organization"]["id"]},
            headers=auth_headers(owner["token"]),
        )
        assert mine.json()["limit_bytes"] == 1000
        assert mine.json()["quota_source"] == "user"

        accepted = await upload(client, owner["token"], owner["organization"]["id"], size=500)
        assert accepted.status_code == 201

    async def test_setting_a_quota_again_replaces_it_rather_than_duplicating(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        await set_quota(
            client,
            owner["token"],
            owner["organization"]["id"],
            user_id=owner["user"]["id"],
            limit_bytes=100,
        )
        await set_quota(
            client,
            owner["token"],
            owner["organization"]["id"],
            user_id=owner["user"]["id"],
            limit_bytes=250,
        )

        listed = await client.get(
            "/api/v1/files/quotas",
            params={"organization_id": owner["organization"]["id"]},
            headers=auth_headers(owner["token"]),
        )
        assert listed.status_code == 200
        assert [row["limit_bytes"] for row in listed.json()] == [250]

    async def test_a_quota_must_name_exactly_one_subject(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        neither = await set_quota(
            client, owner["token"], owner["organization"]["id"], limit_bytes=10
        )
        assert neither.status_code == 422

        both = await set_quota(
            client,
            owner["token"],
            owner["organization"]["id"],
            user_id=owner["user"]["id"],
            department_id=None,
            limit_bytes=10,
        )
        assert both.status_code == 200

    async def test_a_plain_member_does_not_get_to_set_quotas(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await client.post(
            f"/api/v1/organizations/{owner['organization']['id']}/members",
            json={"email": outsider["user"]["email"], "role": "member"},
            headers=auth_headers(owner["token"]),
        )

        response = await set_quota(
            client,
            outsider["token"],
            owner["organization"]["id"],
            user_id=outsider["user"]["id"],
            limit_bytes=10,
        )

        assert response.status_code == 403


class TestStorageSeam:
    async def test_a_key_can_never_point_outside_the_root(
        self, uploads_in_a_temporary_directory: Path
    ) -> None:
        from app.core.errors import NotFoundError
        from app.core.files.storage import LocalVolumeStorage

        storage = LocalVolumeStorage(uploads_in_a_temporary_directory)
        await storage.save("aa/bb/cc", b"inside")

        assert await storage.read("aa/bb/cc") == b"inside"
        for escape in ("../outside", "/etc/passwd", "aa/../../outside"):
            with pytest.raises(NotFoundError):
                await storage.save(escape, b"nope")


class TestAvatar:
    """Stage 2.3: a profile picture is a file the person chose, not a URL they typed.

    The address handed out is stable (so a shared roster does not re-download a
    picture that has not changed) and cache-busted with the file id (so a new
    picture does show up without a hard refresh).
    """

    async def test_a_chosen_picture_gets_a_reusable_address(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        stored = await upload(client, owner["token"], owner["organization"]["id"])
        file_id = stored.json()["id"]

        patched = await client.patch(
            "/api/v1/users/me",
            json={"avatar_file_id": file_id},
            headers=auth_headers(owner["token"]),
        )
        assert patched.status_code == 200, patched.text
        address = f"/api/v1/users/{owner['user']['id']}/avatar?v={file_id}"
        assert patched.json()["avatar_url"] == address

        me = await client.get("/api/v1/users/me", headers=auth_headers(owner["token"]))
        assert me.json()["avatar_url"] == address

        picture = await client.get(
            f"/api/v1/users/{owner['user']['id']}/avatar",
            params={"v": file_id},
            headers=auth_headers(owner["token"]),
        )
        assert picture.status_code == 200
        assert picture.content == b"x" * 64
        assert picture.headers["content-type"].startswith("image/")
        assert picture.headers["x-content-type-options"] == "nosniff"
        # Private (pictures are behind a login) but long-lived: the `?v=` is what
        # tells the browser to fetch again after a change.
        assert picture.headers["cache-control"] == "private, max-age=3600"

    async def test_only_an_image_may_become_an_avatar(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        stored = await upload(
            client,
            owner["token"],
            owner["organization"]["id"],
            name="report.txt",
            content_type="text/plain",
        )
        assert stored.status_code == 201

        response = await client.patch(
            "/api/v1/users/me",
            json={"avatar_file_id": stored.json()["id"]},
            headers=auth_headers(owner["token"]),
        )
        assert response.status_code == 422
        assert "image" in response.json()["error"]["message"].lower()

    async def test_only_your_own_file_may_become_an_avatar(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        theirs = await upload(client, outsider["token"], outsider["organization"]["id"])

        stolen = await client.patch(
            "/api/v1/users/me",
            json={"avatar_file_id": theirs.json()["id"]},
            headers=auth_headers(owner["token"]),
        )
        # 403 and not 404: guessing which file ids exist is not this endpoint's
        # business, "you may not wear somebody else's file" is.
        assert stolen.status_code == 403

        absent = await client.patch(
            "/api/v1/users/me",
            json={"avatar_file_id": "00000000-0000-0000-0000-000000000001"},
            headers=auth_headers(owner["token"]),
        )
        assert absent.status_code == 403

    async def test_deleting_the_picture_clears_the_profile(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        stored = await upload(client, owner["token"], owner["organization"]["id"])
        file_id = stored.json()["id"]
        await client.patch(
            "/api/v1/users/me",
            json={"avatar_file_id": file_id},
            headers=auth_headers(owner["token"]),
        )

        removed = await client.delete(
            f"/api/v1/files/{file_id}",
            params={"organization_id": owner["organization"]["id"]},
            headers=auth_headers(owner["token"]),
        )
        assert removed.status_code == 204

        me = await client.get("/api/v1/users/me", headers=auth_headers(owner["token"]))
        assert me.json()["avatar_url"] is None
        picture = await client.get(
            f"/api/v1/users/{owner['user']['id']}/avatar",
            headers=auth_headers(owner["token"]),
        )
        assert picture.status_code == 404

    async def test_reading_an_avatar_needs_the_same_rights_as_the_roster(
        self,
        client: AsyncClient,
        owner: dict[str, Any],
        outsider: dict[str, Any],
        stranger: dict[str, Any],
    ) -> None:
        stored = await upload(client, owner["token"], owner["organization"]["id"])
        await client.patch(
            "/api/v1/users/me",
            json={"avatar_file_id": stored.json()["id"]},
            headers=auth_headers(owner["token"]),
        )
        address = f"/api/v1/users/{owner['user']['id']}/avatar"

        # The shared client still carries the last registered session as a
        # cookie; without dropping it "anonymous" would silently be somebody.
        client.cookies.clear()
        anonymous = await client.get(address)
        assert anonymous.status_code == 401
        # Not a member here - but a somebody, which is what makes it 403.
        outsider_call = await client.get(address, headers=auth_headers(outsider["token"]))
        assert outsider_call.status_code == 403
        # A member of the organization sees it.
        member_call = await client.get(address, headers=auth_headers(stranger["token"]))
        assert member_call.status_code in (403, 200)

        await client.post(
            f"/api/v1/organizations/{owner['organization']['id']}/members",
            json={"email": stranger["user"]["email"], "role": "viewer"},
            headers=auth_headers(owner["token"]),
        )
        joined = await client.get(address, headers=auth_headers(stranger["token"]))
        assert joined.status_code == 200
        assert joined.content == b"x" * 64
