"""a deputy for a department, not only for a person

A department can name somebody to act while its head is away, and the chart
needs to show that on the collapsed card. There was no place to record it:
`org_deputies` relates two people, and the head of a unit is not the unit.

The relation is many-to-many in the same way the personal one is - two deputies
while they are out, one person acting for several units - so it gets its own
table rather than a column of ids on `org_departments`.

Revision ID: b4e7c1d92a35
Revises: c9f2e6b10d84
Create Date: 2026-10-11

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b4e7c1d92a35"
down_revision: str | None = "c9f2e6b10d84"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "org_department_deputies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("deputy_id", sa.Uuid(), nullable=False),
        sa.Column(
            "added_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_org_department_deputies_organization_id"),
            ondelete="CASCADE",
        ),
        # CASCADE, not SET NULL: a deputy row pointing at a department that no
        # longer exists would be found later against nothing, and nobody would be
        # able to say whose deputy it was meant to be.
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["org_departments.id"],
            name=op.f("fk_org_department_deputies_department_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["deputy_id"],
            ["users.id"],
            name=op.f("fk_org_department_deputies_deputy_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_org_department_deputies")),
        # A repeated add returns the existing row instead of failing on the
        # constraint, which is what the service relies on.
        sa.UniqueConstraint(
            "organization_id",
            "department_id",
            "deputy_id",
            name="uq_org_department_deputy",
        ),
    )
    op.create_index(
        "ix_org_department_deputies_department_id",
        "org_department_deputies",
        ["department_id"],
    )
    op.create_index(
        "ix_org_department_deputies_deputy_id",
        "org_department_deputies",
        ["deputy_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_org_department_deputies_deputy_id", table_name="org_department_deputies")
    op.drop_index("ix_org_department_deputies_department_id", table_name="org_department_deputies")
    op.drop_table("org_department_deputies")
