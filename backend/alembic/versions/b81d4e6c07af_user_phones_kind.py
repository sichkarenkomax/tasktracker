"""phones: the free-text comment becomes a closed kind (stage 2.8)

``user_phones.comment`` was doing two jobs - saying what a number is for, and
being somewhere to write a note - and a note nobody reads is where a phone number
goes to be forgotten. The column becomes ``kind`` with the four values the screen
offers, so the reader sees "work" beside three numbers instead of guessing from
whatever was typed.

Existing rows are mapped by keyword: anything mentioning work becomes ``work``,
home/dom/дом becomes ``home``, mobile/cell becomes ``mobile``, and anything the
mapping does not recognise becomes ``work`` as well. That is a real loss of the
old text, and it is the right one: with the field closed, text nobody can
predict is text nobody can read back.

The number column is untouched and stays as it was written (2.8 stores digits
and a leading ``+``); only the column next to it changes.

Revision ID: b81d4e6c07af
Revises: f3a91c74e2d5
Create Date: 2026-10-10

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b81d4e6c07af"
down_revision: str | None = "f3a91c74e2d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The same four values the model declares, as a CHECK constraint: this project
#: stores enums as VARCHAR + CHECK (docs/architecture.md, section 46) so that
#: adding a value later is an ordinary constraint change.
KINDS = ("work", "home", "mobile", "other")


def upgrade() -> None:
    op.add_column(
        "user_phones",
        sa.Column(
            "kind",
            sa.String(length=16),
            nullable=False,
            server_default="work",
        ),
    )
    op.create_check_constraint("ck_user_phones_kind", "user_phones", sa.column("kind").in_(KINDS))
    op.execute(
        """
        UPDATE user_phones
        SET kind = CASE
            WHEN comment ~* '(home|dom|дом|квартир)' THEN 'home'
            WHEN comment ~* '(mobile|cell|мобил)' THEN 'mobile'
            ELSE 'work'
        END
        WHERE comment IS NOT NULL
        """
    )
    op.drop_column("user_phones", "comment")


def downgrade() -> None:
    op.add_column("user_phones", sa.Column("comment", sa.String(length=120), nullable=True))
    op.execute("UPDATE user_phones SET comment = kind WHERE kind <> 'other'")
    op.drop_constraint("ck_user_phones_kind", "user_phones", type_="check")
    op.drop_column("user_phones", "kind")
