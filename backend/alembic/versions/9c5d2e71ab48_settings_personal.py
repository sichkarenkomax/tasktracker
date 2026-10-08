"""settings: personal settings for one member of one organization

The organization table already answers "how is this portal configured"; this one
answers "how does this person want it", scoped by organization as well as by user
because a personal setting is a statement about the tenant it was set in.

``locale`` and ``theme`` are the keys the preferences screen declares. They are
read from the browser in v1 (stage 1.1 - the first paint must not wait on a round
trip), so no row is written yet; the table and the key registry exist so that a
key which *does* become significant - notification preferences, a module's own
settings - has a place to land that is per user rather than per portal.

Revision ID: 9c5d2e71ab48
Revises: 3f1c7ad92b40
Create Date: 2026-10-08

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "9c5d2e71ab48"
down_revision: str | None = "3f1c7ad92b40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column(
            "value",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_user_settings_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        # Deleting an account takes its preferences with it; a settings row that
        # outlived its owner would be addressable by nobody and orphaned by both.
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_settings_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_settings")),
        sa.UniqueConstraint(
            "organization_id", "user_id", "key", name="uq_user_setting_org_user_key"
        ),
    )
    op.create_index(
        "ix_user_settings_organization_id", "user_settings", ["organization_id"], unique=False
    )
    op.create_index("ix_user_settings_user_id", "user_settings", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_settings_user_id", table_name="user_settings")
    op.drop_index("ix_user_settings_organization_id", table_name="user_settings")
    op.drop_table("user_settings")
