"""files: stored bytes and the three storage limits

Two tables. ``files`` is the only thing that knows where a file's bytes are: it
records the storage key the service generated, so a download addresses a file by
database id and never by a path a caller supplied.

``storage_quotas`` holds the two allowances that are overrides - a department's
and a person's. The portal's own total and its per-file cap stay in the
organization settings, where every other installation-wide number already lives,
and a quota row names exactly one subject so that a limit nobody can explain can
never be stored.

The check constraint is the part worth writing down: a row with both a
department and a person, or with neither, would be a limit whose subject has to
be guessed at, so it is refused by the database rather than by a convention.

Revision ID: b48f0a6d1c77
Revises: 9c5d2e71ab48
Create Date: 2026-10-08

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b48f0a6d1c77"
down_revision: str | None = "9c5d2e71ab48"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "files",
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
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_files_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_files_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_files")),
        # The key is what finds the bytes, so two rows sharing one would make
        # "which file did you delete" answerable two ways.
        sa.UniqueConstraint("storage_key", name=op.f("uq_files_storage_key")),
    )
    op.create_index("ix_files_organization_id", "files", ["organization_id"], unique=False)
    op.create_index("ix_files_owner_id", "files", ["owner_id"], unique=False)

    op.create_table(
        "storage_quotas",
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
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("limit_bytes", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_storage_quotas_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["org_departments.id"],
            name=op.f("fk_storage_quotas_department_id_org_departments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_storage_quotas_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_storage_quotas")),
        sa.CheckConstraint(
            "(department_id IS NOT NULL) <> (user_id IS NOT NULL)",
            name=op.f("ck_storage_quotas_one_subject"),
        ),
        sa.CheckConstraint("limit_bytes >= 0", name=op.f("ck_storage_quotas_limit_bytes")),
    )
    op.create_index(
        "ix_storage_quotas_organization_id", "storage_quotas", ["organization_id"], unique=False
    )
    op.create_index(
        "ix_storage_quotas_department_id", "storage_quotas", ["department_id"], unique=False
    )
    op.create_index("ix_storage_quotas_user_id", "storage_quotas", ["user_id"], unique=False)

    # One allowance per subject. A partial unique index rather than a composite
    # one over (organization, department, user), because a composite would treat
    # the NULL in the unused column as equal-but-unknown and let a second row
    # for the same department in.
    op.create_index(
        "uq_storage_quotas_department",
        "storage_quotas",
        ["organization_id", "department_id"],
        unique=True,
        postgresql_where=sa.text("department_id IS NOT NULL"),
    )
    op.create_index(
        "uq_storage_quotas_user",
        "storage_quotas",
        ["organization_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_storage_quotas_user", table_name="storage_quotas")
    op.drop_index("uq_storage_quotas_department", table_name="storage_quotas")
    op.drop_index("ix_storage_quotas_user_id", table_name="storage_quotas")
    op.drop_index("ix_storage_quotas_department_id", table_name="storage_quotas")
    op.drop_index("ix_storage_quotas_organization_id", table_name="storage_quotas")
    op.drop_table("storage_quotas")

    op.drop_index("ix_files_owner_id", table_name="files")
    op.drop_index("ix_files_organization_id", table_name="files")
    op.drop_table("files")
