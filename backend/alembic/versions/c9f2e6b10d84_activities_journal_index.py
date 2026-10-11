"""activities: a composite index for one person's journal (stage 2.11)

The feed is read three ways: the whole organization by time, one person by time,
and one action. The first had `(organization_id, created_at)` and the third an
index on `action`, but the second - the journal on a member's profile - was left
with an index on `actor_id` alone.

That index finds the rows and then filters and sorts them: the actor's events in
every other organization come back with the rows, and the ordering is done by the
planner rather than by the index. On a small installation nobody notices, and the
journal is exactly the screen that grows with the installation.

`CONCURRENTLY` because `activities` is the largest table here and the column set
is unchanged - adding the index to the model without this would rebuild it while
the service is running.

Revision ID: c9f2e6b10d84
Revises: e5b2f81a07c3
Create Date: 2026-10-11

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "c9f2e6b10d84"
down_revision: str | None = "e5b2f81a07c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "ix_activities_organization_id_actor_id_created_at"


def upgrade() -> None:
    # `CONCURRENTLY` cannot run inside a transaction, and Alembic wraps a
    # migration in one by default - hence `autocommit_block`, which is the
    # documented way to say "this statement is its own transaction". The cost is
    # that a failure between the two halves leaves an invalid index behind;
    # `REINDEX` fixes that, which is a much smaller problem than blocking writes
    # on the largest table in the installation.
    with op.get_context().autocommit_block():
        op.create_index(
            INDEX,
            "activities",
            ["organization_id", "actor_id", "created_at"],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(INDEX, table_name="activities", postgresql_concurrently=True)
