"""Departments, positions, reporting lines and deputies.

Four tables, and the interesting decisions are the ones about what does *not*
exist. A position is not a member and a member is not a position: joining them
would allow a job to be staffed by somebody who has left. A deputy is not a
manager: "covers while I am away" and "reports to" are different facts, and one
cannot be derived from the other.

The org chart itself is two trees that happen to share a node set - the
department tree and the reporting tree - and the editor in the frontend draws
both. Only the department tree is hierarchical in the database; the reporting
line is a single nullable pointer per member, because that is exactly the shape
of "reports to" and a separate table would only add a join to say the same thing.

Revision ID: 7b2a9e41c5d8
Revises: e18d4c7f2b91
Create Date: 2026-10-07

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7b2a9e41c5d8"
down_revision: str | None = "e18d4c7f2b91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- departments ---------------------------------------------------------
    # Created before the member columns that reference it, and after
    # organizations, which every row below cascades from.
    op.create_table(
        "org_departments",
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
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        # Self-referencing. SET NULL rather than CASCADE: deleting a parent must
        # not take its children with it, because those children are real units
        # that happen to be promoted rather than destroyed. The service re-points
        # them at the grandparent before the delete anyway.
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("head_id", sa.Uuid(), nullable=True),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_org_departments_organization_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["org_departments.id"],
            name=op.f("fk_org_departments_parent_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["head_id"], ["users.id"], name=op.f("fk_org_departments_head_id"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_org_departments")),
        # A tenant cannot have two departments with the same name. Without this the
        # editor would happily create "Backend" twice and the chart would show two
        # boxes nobody can tell apart.
        sa.UniqueConstraint("organization_id", "name", name="uq_org_department_org_name"),
    )
    op.create_index("ix_org_departments_organization_id", "org_departments", ["organization_id"])
    op.create_index("ix_org_departments_parent_id", "org_departments", ["parent_id"])

    # --- positions -----------------------------------------------------------
    op.create_table(
        "org_positions",
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
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        # Null is meaningful: it makes the title organization-wide, which is right
        # for the few roles above the departments.
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_org_positions_organization_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["org_departments.id"],
            name=op.f("fk_org_positions_department_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_org_positions")),
        sa.UniqueConstraint("organization_id", "title", name="uq_org_position_org_title"),
    )
    op.create_index("ix_org_positions_organization_id", "org_positions", ["organization_id"])
    op.create_index("ix_org_positions_department_id", "org_positions", ["department_id"])

    # --- deputies ------------------------------------------------------------
    # Created last: it references both users and the organization, and nothing
    # references it.
    op.create_table(
        "org_deputies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("deputy_id", sa.Uuid(), nullable=False),
        sa.Column(
            "added_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_org_deputies_organization_id"),
            ondelete="CASCADE",
        ),
        # CASCADE, not SET NULL: a deputy record that outlived both of the people
        # it is about would be a row nothing could ever explain.
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_org_deputies_user_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["deputy_id"], ["users.id"], name=op.f("fk_org_deputies_deputy_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_org_deputies")),
        # Makes a repeated add return the existing row rather than fail on the
        # constraint, which is what the service relies on.
        sa.UniqueConstraint(
            "organization_id", "user_id", "deputy_id", name="uq_org_deputy_user_deputy"
        ),
    )
    op.create_index("ix_org_deputies_user_id", "org_deputies", ["user_id"])
    op.create_index("ix_org_deputies_deputy_id", "org_deputies", ["deputy_id"])

    # --- where a member sits -------------------------------------------------
    # Added in one ALTER so the membership row is never momentarily inconsistent:
    # there is no window in which a person is in a department that does not exist.
    #
    # All three are SET NULL. Losing a department, a position or a manager must
    # leave the person employed and unplaced, never delete them.
    op.add_column("organization_members", sa.Column("department_id", sa.Uuid(), nullable=True))
    op.add_column("organization_members", sa.Column("position_id", sa.Uuid(), nullable=True))
    op.add_column("organization_members", sa.Column("manager_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_org_members_department_id"),
        "organization_members",
        "org_departments",
        ["department_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_org_members_position_id"),
        "organization_members",
        "org_positions",
        ["position_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_org_members_manager_id"),
        "organization_members",
        "users",
        ["manager_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # The chart is read as "everyone in this department" and "everyone reporting
    # to this person", so both columns get their own index.
    op.create_index(
        "ix_organization_members_department_id", "organization_members", ["department_id"]
    )
    op.create_index("ix_organization_members_manager_id", "organization_members", ["manager_id"])


def downgrade() -> None:
    op.drop_index("ix_organization_members_manager_id", table_name="organization_members")
    op.drop_index("ix_organization_members_department_id", table_name="organization_members")
    op.drop_constraint(
        op.f("fk_org_members_manager_id"), "organization_members", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_org_members_position_id"), "organization_members", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_org_members_department_id"), "organization_members", type_="foreignkey"
    )
    op.drop_column("organization_members", "manager_id")
    op.drop_column("organization_members", "position_id")
    op.drop_column("organization_members", "department_id")

    op.drop_index("ix_org_deputies_deputy_id", table_name="org_deputies")
    op.drop_index("ix_org_deputies_user_id", table_name="org_deputies")
    op.drop_table("org_deputies")

    op.drop_index("ix_org_positions_department_id", table_name="org_positions")
    op.drop_index("ix_org_positions_organization_id", table_name="org_positions")
    op.drop_table("org_positions")

    op.drop_index("ix_org_departments_parent_id", table_name="org_departments")
    op.drop_index("ix_org_departments_organization_id", table_name="org_departments")
    op.drop_table("org_departments")
