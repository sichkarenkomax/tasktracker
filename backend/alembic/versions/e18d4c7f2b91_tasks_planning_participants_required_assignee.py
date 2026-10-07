"""tasks: responsible person, participants, planning, a fourth status

Four changes that belong together because they all touch the same table and the
same product decision - a task is somebody's work, planned for a period of time,
with more than one person possibly involved.

* ``assignee_id`` becomes NOT NULL. The existing rows are filled with their own
  creator first, so the constraint holds and no task is left without somebody on
  it. The foreign key also switches from SET NULL to RESTRICT: losing an account
  must not be able to leave a task with nobody responsible, which the column now
  forbids anyway.
* ``task_participants`` - co-assignees and watchers. One table with a role column
  rather than two tables, because add, remove, list and authorize are identical
  for both and two tables would mean writing all four twice. The reporter is not
  here; it is the creator, already on the task.
* Planning: ``planned_start``, ``planned_end``, ``planned_duration`` and
  ``duration_unit``. A single deadline column could not answer "when does this
  begin", and computing the end on every read means two readers at two moments get
  two answers.
* ``deferred`` joins the statuses. ``value_enum`` stores a VARCHAR with a CHECK, so
  this is a constraint change and not an ALTER TYPE - which is exactly the
  flexibility section 15 asked for when it allowed custom statuses later.

Revision ID: e18d4c7f2b91
Revises: c4f1b7e29a03
Create Date: 2026-10-06

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e18d4c7f2b91"
down_revision: str | None = "c4f1b7e29a03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- the responsible person becomes mandatory ----------------------------
    # Order matters: fill the holes before the constraint, or the ALTER fails and
    # the operator is left guessing which rows were the problem.
    op.execute("UPDATE tasks SET assignee_id = creator_id WHERE assignee_id IS NULL")

    op.alter_column("tasks", "assignee_id", existing_type=sa.Uuid(), nullable=False)

    # SET NULL would have left a task with nobody on it the moment an account was
    # deleted, which is exactly what the NOT NULL above forbids.
    op.drop_constraint(op.f("fk_tasks_assignee_id_users"), "tasks", type_="foreignkey")
    op.create_foreign_key(
        op.f("fk_tasks_assignee_id_users"),
        "tasks",
        "users",
        ["assignee_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # --- planning -------------------------------------------------------------
    op.add_column("tasks", sa.Column("planned_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("planned_end", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("planned_duration", sa.Integer(), nullable=True))
    op.add_column(
        "tasks",
        sa.Column(
            "duration_unit",
            sa.String(length=16),
            server_default="hours",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_tasks_duration_unit"),
        "tasks",
        sa.column("duration_unit").in_(["minutes", "hours", "days", "weeks", "months"]),
    )
    op.create_check_constraint(
        op.f("ck_tasks_planned_duration"),
        "tasks",
        "planned_duration IS NULL OR planned_duration >= 0",
    )
    # The invariant the service enforces, expressed where the database can see it
    # too: an end before its own start is never right.
    op.create_check_constraint(
        op.f("ck_tasks_planned_window"),
        "tasks",
        "planned_start IS NULL OR planned_end IS NULL OR planned_end >= planned_start",
    )

    # The Gantt and calendar read the window; both filter by start, order by end.
    op.create_index(
        "ix_tasks_organization_id_planned_start",
        "tasks",
        ["organization_id", "planned_start"],
        unique=False,
    )
    op.create_index("ix_tasks_planned_end", "tasks", ["planned_end"], unique=False)

    # --- a fourth status ------------------------------------------------------
    # `value_enum` stores VARCHAR plus a CHECK rather than a native enum, so a new
    # status is a constraint change and not an ALTER TYPE that cannot be reversed
    # on older PostgreSQL. Raw SQL rather than `create_check_constraint` because the
    # metadata naming convention would prefix the name we drop, and a CHECK cannot
    # be amended - only dropped and recreated under exactly the same name.
    op.execute("ALTER TABLE tasks DROP CONSTRAINT IF EXISTS ck_tasks_task_status")
    op.execute(
        "ALTER TABLE tasks ADD CONSTRAINT ck_tasks_task_status "
        "CHECK (status IN ('todo', 'in_progress', 'deferred', 'done'))"
    )

    # --- participants ---------------------------------------------------------
    op.create_table(
        "task_participants",
        sa.Column("id", sa.Uuid(), nullable=False),
        # TimestampMixin stamps both in Python *and* leaves a server default, so
        # a row written by a script or by psql still gets a time. Autogenerate
        # compares the default as well as the type, so it has to be declared here.
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
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_task_participants_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_task_participants_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_participants")),
        # The unique index is what makes a duplicate add fail rather than the
        # application having to check first.
        sa.UniqueConstraint(
            "task_id", "user_id", "role", name="uq_task_participants_task_user_role"
        ),
        sa.CheckConstraint(
            "role IN ('co_assignee', 'watcher')", name=op.f("ck_task_participants_role")
        ),
    )
    op.create_index("ix_task_participants_task_id", "task_participants", ["task_id"], unique=False)
    op.create_index("ix_task_participants_user_id", "task_participants", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_task_participants_user_id", table_name="task_participants")
    op.drop_index("ix_task_participants_task_id", table_name="task_participants")
    op.drop_table("task_participants")

    op.execute("ALTER TABLE tasks DROP CONSTRAINT IF EXISTS ck_tasks_task_status")
    op.execute(
        "ALTER TABLE tasks ADD CONSTRAINT ck_tasks_task_status "
        "CHECK (status IN ('todo', 'in_progress', 'done'))"
    )
    # A task parked as "deferred" goes back to "todo" rather than vanishing:
    # dropping the constraint is not the same as losing the work.
    op.execute("UPDATE tasks SET status = 'todo' WHERE status = 'deferred'")

    op.drop_index("ix_tasks_planned_end", table_name="tasks")
    op.drop_index("ix_tasks_organization_id_planned_start", table_name="tasks")
    op.drop_constraint(op.f("ck_tasks_planned_window"), "tasks", type_="check")
    op.drop_constraint(op.f("ck_tasks_planned_duration"), "tasks", type_="check")
    op.drop_constraint(op.f("ck_tasks_duration_unit"), "tasks", type_="check")
    op.drop_column("tasks", "duration_unit")
    op.drop_column("tasks", "planned_duration")
    op.drop_column("tasks", "planned_end")
    op.drop_column("tasks", "planned_start")

    # The constraint has to be dropped before another one with the same name can
    # exist on the same column; creating it directly is a duplicate-object error.
    op.drop_constraint(op.f("fk_tasks_assignee_id_users"), "tasks", type_="foreignkey")
    op.create_foreign_key(
        op.f("fk_tasks_assignee_id_users"),
        "tasks",
        "users",
        ["assignee_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column("tasks", "assignee_id", existing_type=sa.Uuid(), nullable=True)
