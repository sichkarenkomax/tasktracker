"""tasks: a task may exist without a project

Section 30 wants a task list as the product's home screen. With ``project_id``
mandatory, a new account had to create a project before it could record anything,
so the first screen a person met was a project form rather than their work.

The column becomes nullable and gains a partial index for the inbox view, which
is the query that now runs on every page load: tasks in this organization with
no project at all.

Revision ID: c4f1b7e29a03
Revises: dea9abae1794
Create Date: 2026-10-06

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import Connection

from alembic import op

revision: str = "c4f1b7e29a03"
down_revision: str | None = "dea9abae1794"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The organization column stays NOT NULL, so tenant isolation still does not
    # depend on the project: an unfiled task is still somebody's work.
    op.alter_column(
        "tasks",
        "project_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    # A plain b-tree index on a column that is NULL for every inbox row is mostly
    # dead weight; this one only indexes the rows the inbox actually reads.
    op.create_index(
        "ix_tasks_organization_id_unfiled",
        "tasks",
        ["organization_id"],
        unique=False,
        postgresql_where=sa.text("project_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_organization_id_unfiled", table_name="tasks")

    # Rows created without a project have nowhere to go back to. Saying so is
    # better than failing on a NOT NULL violation from inside ALTER, which tells
    # the operator nothing about what to fix.
    bind: Connection = op.get_bind()
    orphans = bind.execute(
        sa.text("SELECT count(*) FROM tasks WHERE project_id IS NULL")
    ).scalar_one()
    if orphans:
        raise RuntimeError(
            f"Cannot revert: {orphans} task(s) are not filed under any project. "
            "Assign them to a project first."
        )

    op.alter_column(
        "tasks",
        "project_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
