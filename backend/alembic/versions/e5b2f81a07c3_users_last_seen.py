"""users: when a person was last here (stage 2.9)

`last_login_at` says when somebody last proved they knew their password. This
says when they were last *here*, which is a different and a more useful question:
a person who is signed in all afternoon has not signed in since this morning.

It is written from ordinary API requests, throttled to one write per minute per
person - see `users.presence`. The risk the roadmap named for this is real: a
column updated on every request turns every read into a write, and the writes are
the expensive part. The throttle is a condition of the feature, not an
optimization of it.

Nullable, and nothing backfills it: everybody was "last seen" at a time nobody
recorded, and inventing one would make the whole roster look freshly active on
the morning the column is deployed.

Revision ID: e5b2f81a07c3
Revises: a1d7c4e90f23
Create Date: 2026-10-10

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e5b2f81a07c3"
down_revision: str | None = "a1d7c4e90f23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "last_seen")
