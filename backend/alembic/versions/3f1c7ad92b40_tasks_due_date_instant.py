"""tasks: the deadline becomes an instant

``due_date`` was a ``Date`` while the only calendar in the product was the
browser's own. That calendar cannot be themed (Chromium paints its popup itself
and ignores ``accent-color``, proven on Chrome 154), so the deadline got a date
picker of ours - and a picker of ours can offer a time of day, which "hand it in
by 18:00" needs. A time of day cannot live in a ``Date``.

The cast sends every existing deadline to midnight UTC on the day it already had,
which is the only reading a bare date has. For a reader west of Greenwich a
deadline that had no time will display on the previous evening; deadlines set
after this migration carry a real time and are unaffected. The alternative -
keeping the date and adding an optional time column - was rejected in favour of
one instant that "overdue" and the list's date filters can compare directly.

Revision ID: 3f1c7ad92b40
Revises: 7b2a9e41c5d8
Create Date: 2026-10-08

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "3f1c7ad92b40"
down_revision: str | None = "7b2a9e41c5d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # USING is required: PostgreSQL will not cast date to timestamptz implicitly,
    # and without it the ALTER fails on a table that has rows.
    op.alter_column(
        "tasks",
        "due_date",
        type_=postgresql.TIMESTAMP(timezone=True),
        existing_type=sa.Date(),
        existing_nullable=True,
        postgresql_using="due_date::timestamptz",
    )


def downgrade() -> None:
    # The time of day has nowhere to go, so the day is kept and the time dropped.
    # Reading it back in the database's zone is the same choice the upgrade made
    # for deadlines that had no time at all.
    op.alter_column(
        "tasks",
        "due_date",
        type_=sa.Date(),
        existing_type=postgresql.TIMESTAMP(timezone=True),
        existing_nullable=True,
        postgresql_using="due_date::date",
    )
