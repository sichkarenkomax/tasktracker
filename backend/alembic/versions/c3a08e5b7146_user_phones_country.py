"""phones: the country the number is read in (stage 2.8)

The mask cannot be right without it. `8 900 123-45-67`, `8 (900) 123-45-67` and
`+7 900 123 45 67` are one call written three ways, and a number stored in
E.164 is unreadable in a national format until somebody says which country they
are in.

Nullable, and existing rows stay NULL. They are shown in the international form,
which is the one shape that cannot be misread - guessing a country for a number
that was typed before this column existed would put somebody else's digits into
somebody's national format, which is worse than no format at all.

Revision ID: c3a08e5b7146
Revises: b81d4e6c07af
Create Date: 2026-10-10

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3a08e5b7146"
down_revision: str | None = "b81d4e6c07af"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_phones", sa.Column("country", sa.String(length=2), nullable=True))


def downgrade() -> None:
    op.drop_column("user_phones", "country")
