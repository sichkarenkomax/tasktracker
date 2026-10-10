"""phones: one row per number per person (stage 2.8)

A duplicate is not two numbers, it is one number written twice. The service
refuses to create one now; this is what makes sure the data that predates that
refusal cannot sit there forever, and that a race between two requests cannot
create one either.

Duplicates are collapsed before the constraint goes on, keeping the oldest row:
the first number a person wrote is the one they still recognise, and the kind on
it is the older statement about it. A person with the same number twice in an
older install keeps one number, not none - which is the whole reason this is a
migration rather than an assertion.

Revision ID: a1d7c4e90f23
Revises: c3a08e5b7146
Create Date: 2026-10-10

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a1d7c4e90f23"
down_revision: str | None = "c3a08e5b7146"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM user_phones older
        USING user_phones newer
        WHERE older.user_id = newer.user_id
          AND older.number = newer.number
          AND (older.created_at, older.id) > (newer.created_at, newer.id)
        """
    )
    op.create_unique_constraint(
        "uq_user_phones_user_id_number", "user_phones", ["user_id", "number"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_user_phones_user_id_number", "user_phones", type_="unique")
