"""users: a birthday, and the phones that go with it (stage 2.8)

The two contact details a colleague actually needs, and nothing derived from
them: no age column, no "turns 40 next month", no sort key that would make the
year mandatory. A person who does not want their year published simply leaves
it out, and the date column stays nullable so "I did not tell you" cannot be
mistaken for "the year is 1970".

``user_phones`` is a table because one number is rarely the whole answer. The
comment sits on the row rather than on the user, so it follows its own number
when that number is edited or deleted. ``ON DELETE CASCADE`` says what deleting
an account means without anyone having to remember to clear phones by hand.

The composite index on ``(user_id, created_at)`` is the one query this table
serves - "this person's numbers, oldest first" - which is also the order the
screen shows them in.

Revision ID: f3a91c74e2d5
Revises: c9e5a7d3f8b2
Create Date: 2026-10-10

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f3a91c74e2d5"
down_revision: str | None = "c9e5a7d3f8b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("birthday", sa.Date(), nullable=True))

    op.create_table(
        "user_phones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_phones_user_id", "user_phones", ["user_id"], unique=False)
    op.create_index(
        "ix_user_phones_user_id_created_at",
        "user_phones",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_phones_user_id_created_at", table_name="user_phones")
    op.drop_index("ix_user_phones_user_id", table_name="user_phones")
    op.drop_table("user_phones")
    op.drop_column("users", "birthday")
