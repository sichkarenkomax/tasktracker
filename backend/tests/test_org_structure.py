"""Organization structure: departments, positions, reporting lines, deputies.

The rules worth testing are the ones the database cannot enforce. Foreign keys
guarantee that a department's parent exists and that a manager is somebody; only
the service can know that the parent is not *below* the child, which is the
difference between a tree and a loop. Those tests are here, along with the tenant
boundary - a chart that leaked another organization's structure would be a
worse bug than a missing feature.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.conftest import auth_headers


async def _add_member(
    client: AsyncClient, owner: dict[str, Any], account: dict[str, Any], role: str = "member"
) -> str:
    response = await client.post(
        f"/api/v1/organizations/{owner['organization']['id']}/members",
        json={"email": account["user"]["email"], "role": role},
        headers=auth_headers(owner["token"]),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["user_id"])


async def _department(
    client: AsyncClient, owner: dict[str, Any], name: str, **body: Any
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/organizations/{owner['organization']['id']}/departments",
        json={"name": name, **body},
        headers=auth_headers(owner["token"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _position(
    client: AsyncClient, owner: dict[str, Any], title: str, **body: Any
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/organizations/{owner['organization']['id']}/positions",
        json={"title": title, **body},
        headers=auth_headers(owner["token"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _place(client: AsyncClient, owner: dict[str, Any], user_id: str, **body: Any) -> Any:
    return await client.patch(
        f"/api/v1/organizations/{owner['organization']['id']}/members/{user_id}/placement",
        json=body,
        headers=auth_headers(owner["token"]),
    )


class TestDepartments:
    async def test_create_and_read_back(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        department = await _department(client, owner, "Engineering")

        assert department["name"] == "Engineering"
        assert department["parent_id"] is None
        assert department["position"] == 0

    async def test_nesting(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        parent = await _department(client, owner, "Engineering")
        child = await _department(client, owner, "Backend", parent_id=parent["id"])

        assert child["parent_id"] == parent["id"]

    async def test_siblings_keep_their_order(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Insertion order, not alphabetical: the order somebody arranged is the
        order they want to read, and re-reading a chart in a different order every
        time a name starts with an earlier letter would be its own bug."""
        first = await _department(client, owner, "Zebra")
        second = await _department(client, owner, "Alpha")

        assert first["position"] < second["position"]

    async def test_same_name_twice_is_refused(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        await _department(client, owner, "Engineering")

        response = await client.post(
            f"/api/v1/organizations/{owner['organization']['id']}/departments",
            json={"name": "Engineering"},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 409

    async def test_the_same_name_is_refused_anywhere_in_the_organization(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Names are unique per organization, not per parent.

        Two boxes on the chart both reading "Backend", one nested and one not,
        cannot be told apart by a reader - and the editor would offer no way to
        tell them apart later either. This pins the decision; changing it is a
        migration, not a bug fix.
        """
        await _department(client, owner, "Engineering")
        product = await _department(client, owner, "Product")

        response = await client.post(
            f"/api/v1/organizations/{owner['organization']['id']}/departments",
            json={"name": "Engineering", "parent_id": product["id"]},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 409

    async def test_a_department_cannot_be_its_own_parent(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        department = await _department(client, owner, "Engineering")

        response = await client.patch(
            f"/api/v1/organizations/{owner['organization']['id']}/departments/{department['id']}",
            json={"parent_id": department["id"]},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 422

    async def test_a_department_cannot_move_below_its_own_child(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The loop the database cannot see: `a -> b -> a` satisfies every foreign
        key and hangs every reader that walks the tree."""
        engineering = await _department(client, owner, "Engineering")
        backend = await _department(client, owner, "Backend", parent_id=engineering["id"])

        response = await client.patch(
            f"/api/v1/organizations/{owner['organization']['id']}/departments/{engineering['id']}",
            json={"parent_id": backend["id"]},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 422
        assert "loop" in response.json()["error"]["message"].lower()

    async def test_a_loop_is_refused_however_deep_it_is(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        a = await _department(client, owner, "A")
        b = await _department(client, owner, "B", parent_id=a["id"])
        c = await _department(client, owner, "C", parent_id=b["id"])

        response = await client.patch(
            f"/api/v1/organizations/{owner['organization']['id']}/departments/{a['id']}",
            json={"parent_id": c["id"]},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 422

    async def test_renaming_leaves_the_parent_alone(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Omitting a nullable field must mean "leave it", not "clear it". Sending
        a name must not silently promote a nested department to the top."""
        parent = await _department(client, owner, "Engineering")
        child = await _department(client, owner, "Backend", parent_id=parent["id"])

        response = await client.patch(
            f"/api/v1/organizations/{owner['organization']['id']}/departments/{child['id']}",
            json={"name": "Platform"},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200
        assert response.json()["parent_id"] == parent["id"]

    async def test_deleting_promotes_children_and_unplaces_people(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        """A person's employment and the neighbouring units outlive this object.
        Deleting a department must not take either with it."""
        department = await _department(client, owner, "Engineering")
        child = await _department(client, owner, "Backend", parent_id=department["id"])
        member_id = await _add_member(client, owner, outsider)
        # In the department about to disappear, not the child: somebody in the
        # child must keep their place, and somebody in the deleted unit must lose
        # theirs.
        await _place(client, owner, member_id, department_id=department["id"])

        response = await client.delete(
            f"/api/v1/organizations/{owner['organization']['id']}/departments/{department['id']}",
            headers=auth_headers(owner["token"]),
        )
        assert response.status_code == 204, response.text

        structure = await client.get(
            f"/api/v1/organizations/{owner['organization']['id']}/structure",
            headers=auth_headers(owner["token"]),
        )
        assert structure.status_code == 200
        body = structure.json()

        remaining = {row["id"]: row for row in body["departments"]}
        assert department["id"] not in remaining
        # The child survives, promoted to the deleted department's level.
        assert remaining[child["id"]]["parent_id"] is None
        # The person survives, unplaced: losing a unit is not losing a job.
        assert body["placements"][member_id]["department_id"] is None

    async def test_head_must_be_a_member(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        department = await _department(client, owner, "Engineering")

        response = await client.patch(
            f"/api/v1/organizations/{owner['organization']['id']}/departments/{department['id']}",
            json={"head_id": outsider["user"]["id"]},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 422


class TestPositions:
    async def test_create(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        department = await _department(client, owner, "Engineering")

        position = await _position(
            client, owner, "Backend developer", department_id=department["id"], rank=3
        )

        assert position["title"] == "Backend developer"
        assert position["department_id"] == department["id"]
        assert position["rank"] == 3

    async def test_organization_wide(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        """A null department is meaningful, not missing: it is how the handful of
        roles above the departments are recorded."""
        position = await _position(client, owner, "Chief executive")

        assert position["department_id"] is None

    async def test_same_title_twice_is_refused(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        await _position(client, owner, "Backend developer")

        response = await client.post(
            f"/api/v1/organizations/{owner['organization']['id']}/positions",
            json={"title": "Backend developer"},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 409

    async def test_ranks_sort_high_first_with_unranked_last(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """A title somebody never ranked must not outrank one somebody did."""
        await _position(client, owner, "Intern")
        await _position(client, owner, "Engineer", rank=1)
        await _position(client, owner, "Director", rank=9)

        response = await client.get(
            f"/api/v1/organizations/{owner['organization']['id']}/structure",
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200
        titles = [row["title"] for row in response.json()["positions"]]
        assert titles == ["Director", "Engineer", "Intern"]

    async def test_deleting_unplaces_the_people_holding_it(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        position = await _position(client, owner, "Backend developer")
        member_id = await _add_member(client, owner, outsider)
        await _place(client, owner, member_id, position_id=position["id"])

        response = await client.delete(
            f"/api/v1/organizations/{owner['organization']['id']}/positions/{position['id']}",
            headers=auth_headers(owner["token"]),
        )
        assert response.status_code == 204, response.text

        structure = await client.get(
            f"/api/v1/organizations/{owner['organization']['id']}/structure",
            headers=auth_headers(owner["token"]),
        )
        assert structure.json()["placements"][member_id]["position_id"] is None


class TestReportingLines:
    async def test_place_a_person(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        department = await _department(client, owner, "Engineering")
        position = await _position(client, owner, "Backend developer")
        member_id = await _add_member(client, owner, outsider)

        response = await _place(
            client,
            owner,
            member_id,
            department_id=department["id"],
            position_id=position["id"],
            manager_id=owner["user"]["id"],
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["department_id"] == department["id"]
        assert body["position_id"] == position["id"]
        assert body["manager_id"] == owner["user"]["id"]

    async def test_nobody_is_their_own_manager(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        response = await _place(client, owner, owner["user"]["id"], manager_id=owner["user"]["id"])

        assert response.status_code == 422
        assert "own manager" in response.json()["error"]["message"]

    async def test_a_manager_must_be_a_member(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        response = await _place(
            client, owner, owner["user"]["id"], manager_id=outsider["user"]["id"]
        )

        assert response.status_code == 422

    async def test_a_reporting_loop_is_refused(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        """Two managers pointing at each other satisfies every foreign key and
        makes the chart impossible to lay out."""
        member_id = await _add_member(client, owner, outsider)
        owner_id = owner["user"]["id"]

        first = await _place(client, owner, member_id, manager_id=owner_id)
        assert first.status_code == 200, first.text

        response = await _place(client, owner, owner_id, manager_id=member_id)

        assert response.status_code == 422
        assert "reports to" in response.json()["error"]["message"]

    async def test_a_loop_is_refused_through_a_chain(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        """A -> B -> C, then A's manager set to C: two hops up, not one."""
        middle = await _add_member(client, owner, outsider)
        other = await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"third-{owner['user']['id']}@example.com",
                "username": f"third{owner['user']['id'][:8]}",
                "password": "sup3r-secret",
            },
        )
        assert other.status_code == 201, other.text
        bottom = str(other.json()["user"]["id"])
        bottom_id = await _add_member(client, owner, other.json())
        assert bottom_id == bottom

        owner_id = owner["user"]["id"]
        assert (await _place(client, owner, middle, manager_id=owner_id)).status_code == 200
        assert (await _place(client, owner, bottom, manager_id=middle)).status_code == 200

        response = await _place(client, owner, owner_id, manager_id=bottom)

        assert response.status_code == 422

    async def test_leaving_the_manager_is_possible(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        """Null here clears the reporting line; it does not remove the person."""
        member_id = await _add_member(client, owner, outsider)
        await _place(client, owner, member_id, manager_id=owner["user"]["id"])

        response = await _place(client, owner, member_id, manager_id=None)

        assert response.status_code == 200
        assert response.json()["manager_id"] is None

    async def test_placing_somebody_outside_the_organization_is_refused(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        response = await client.patch(
            f"/api/v1/organizations/{owner['organization']['id']}"
            f"/members/{outsider['user']['id']}/placement",
            json={"department_id": None},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 404


class TestDeputies:
    async def test_add_and_read(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        member_id = await _add_member(client, owner, outsider)

        response = await client.post(
            f"/api/v1/organizations/{owner['organization']['id']}"
            f"/members/{owner['user']['id']}/deputies",
            json={"deputy_id": member_id},
            headers=auth_headers(owner["token"]),
        )
        assert response.status_code == 201, response.text

        structure = await client.get(
            f"/api/v1/organizations/{owner['organization']['id']}/structure",
            headers=auth_headers(owner["token"]),
        )
        assert structure.json()["placements"][owner["user"]["id"]]["deputies"] == [member_id]

    async def test_nobody_is_their_own_deputy(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        response = await client.post(
            f"/api/v1/organizations/{owner['organization']['id']}"
            f"/members/{owner['user']['id']}/deputies",
            json={"deputy_id": owner["user"]["id"]},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 422

    async def test_a_stranger_is_refused(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        response = await client.post(
            f"/api/v1/organizations/{owner['organization']['id']}"
            f"/members/{owner['user']['id']}/deputies",
            json={"deputy_id": outsider["user"]["id"]},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 422

    async def test_adding_twice_is_harmless(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        member_id = await _add_member(client, owner, outsider)
        url = (
            f"/api/v1/organizations/{owner['organization']['id']}"
            f"/members/{owner['user']['id']}/deputies"
        )
        body = {"deputy_id": member_id}
        headers = auth_headers(owner["token"])

        first = await client.post(url, json=body, headers=headers)
        second = await client.post(url, json=body, headers=headers)

        assert first.status_code == 201
        assert second.status_code == 201

        structure = await client.get(
            f"/api/v1/organizations/{owner['organization']['id']}/structure", headers=headers
        )
        assert structure.json()["placements"][owner["user"]["id"]]["deputies"] == [member_id]

    async def test_remove(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        member_id = await _add_member(client, owner, outsider)
        await client.post(
            f"/api/v1/organizations/{owner['organization']['id']}"
            f"/members/{owner['user']['id']}/deputies",
            json={"deputy_id": member_id},
            headers=auth_headers(owner["token"]),
        )

        response = await client.delete(
            f"/api/v1/organizations/{owner['organization']['id']}"
            f"/members/{owner['user']['id']}/deputies/{member_id}",
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 204

    async def test_removing_something_absent_is_404(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        response = await client.delete(
            f"/api/v1/organizations/{owner['organization']['id']}"
            f"/members/{owner['user']['id']}/deputies/{outsider['user']['id']}",
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 404


class TestPermissions:
    async def test_a_member_may_read_but_not_write(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        """Knowing the structure is not an administrative act. Changing it is."""
        member_id = await _add_member(client, owner, outsider)
        headers = auth_headers(outsider["token"])
        base = f"/api/v1/organizations/{owner['organization']['id']}"

        read = await client.get(f"{base}/structure", headers=headers)
        write = await client.post(f"{base}/departments", json={"name": "Sneaky"}, headers=headers)
        place = await client.patch(
            f"{base}/members/{member_id}/placement", json={"department_id": None}, headers=headers
        )

        assert read.status_code == 200
        assert write.status_code == 403
        assert place.status_code == 403

    async def test_a_viewer_may_read_but_not_write(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await _add_member(client, owner, outsider, role="viewer")
        headers = auth_headers(outsider["token"])
        base = f"/api/v1/organizations/{owner['organization']['id']}"

        assert (await client.get(f"{base}/structure", headers=headers)).status_code == 200

        write = await client.post(f"{base}/positions", json={"title": "Sneaky"}, headers=headers)
        assert write.status_code == 403

    async def test_an_admin_may_write(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await _add_member(client, owner, outsider, role="admin")
        headers = auth_headers(outsider["token"])

        response = await client.post(
            f"/api/v1/organizations/{owner['organization']['id']}/departments",
            json={"name": "Operations"},
            headers=headers,
        )

        assert response.status_code == 201, response.text

    async def test_a_stranger_sees_nothing(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        response = await client.get(
            f"/api/v1/organizations/{owner['organization']['id']}/structure",
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403


class TestTenantBoundary:
    async def test_another_organizations_department_is_invisible(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        """A department id from another tenant does not exist as far as this
        organization is concerned.

        The outsider is the owner of their own organization, so authorization
        passes and the answer comes from the lookup: the route is scoped to the
        organization in the path, so a foreign id matches nothing. 404 rather than
        403 here means "there is no such department for you", not "you may not
        touch that one".
        """
        theirs = await _department(client, owner, "Engineering")

        response = await client.patch(
            f"/api/v1/organizations/{outsider['organization']['id']}/departments/{theirs['id']}",
            json={"name": "Stolen"},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 404

    async def test_a_department_from_another_organization_is_not_found(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        """Inside your own organization, somebody else's id simply does not
        exist. Silently renaming it would be a cross-tenant write."""
        """Inside your own organization, somebody else's id simply does not
        exist. Silently renaming it would be a cross-tenant write.

        The outsider is an admin here, so the permission check passes and this
        test is about the scope of the lookup rather than about the role.
        """
        await _add_member(client, owner, outsider, role="admin")
        # A department of the outsider's own organization, addressed through the
        # owner's path. The outsider may pass the permission check for the owner's
        # organization and still find nothing: the id belongs to another tenant,
        # and a lookup scoped to the path cannot see it.
        theirs = await _department(client, outsider, "Engineering")

        response = await client.patch(
            f"/api/v1/organizations/{owner['organization']['id']}/departments/{theirs['id']}",
            json={"name": "Stolen"},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 404

        # And it really is untouched, rather than merely reported as missing.
        check = await client.get(
            f"/api/v1/organizations/{outsider['organization']['id']}/structure",
            headers=auth_headers(outsider["token"]),
        )
        assert check.json()["departments"][0]["name"] == "Engineering"

    async def test_the_chart_is_scoped_to_its_organization(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await _department(client, owner, "Only Mine")

        response = await client.get(
            f"/api/v1/organizations/{outsider['organization']['id']}/structure",
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 200
        assert response.json()["departments"] == []

    async def test_a_stranger_is_refused_the_whole_chart(
        self, client: AsyncClient, owner: dict[str, Any], stranger: dict[str, Any]
    ) -> None:
        """Belonging to no organization at all is also a refusal, and it is the
        authorization check rather than a missing row that refuses it."""
        await _department(client, owner, "Engineering")

        response = await client.get(
            f"/api/v1/organizations/{owner['organization']['id']}/structure",
            headers=auth_headers(stranger["token"]),
        )

        assert response.status_code == 403


class TestSnapshot:
    async def test_one_request_carries_everything(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        """The editor would otherwise spend a round trip per node before drawing
        anything, and every one of them could see a different version."""
        department = await _department(client, owner, "Engineering")
        position = await _position(
            client, owner, "Backend developer", department_id=department["id"]
        )
        member_id = await _add_member(client, owner, outsider)
        await _place(
            client,
            owner,
            member_id,
            department_id=department["id"],
            position_id=position["id"],
            manager_id=owner["user"]["id"],
        )

        response = await client.get(
            f"/api/v1/organizations/{owner['organization']['id']}/structure",
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200
        body = response.json()
        assert {row["id"] for row in body["departments"]} == {department["id"]}
        assert {row["id"] for row in body["positions"]} == {position["id"]}
        assert len(body["members"]) == 2
        assert body["placements"][member_id]["manager_id"] == owner["user"]["id"]
        # Every member gets a placement, even the ones with nothing recorded:
        # the client should not have to guess which are missing.
        assert set(body["placements"]) == {row["user_id"] for row in body["members"]}
