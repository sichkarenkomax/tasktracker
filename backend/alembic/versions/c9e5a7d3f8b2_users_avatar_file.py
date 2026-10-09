"""users: the avatar becomes a row in files, not a stored URL

``avatar_url`` held whatever the browser had built - a ready-made link that
knew nothing about the file behind it. Deleting that file left the profile
pointing at nothing, and nothing in the schema could say "this file *is* a
person's picture". The column is replaced by a reference to ``files``, which
answers both: the database knows, and ``ON DELETE SET NULL`` makes removing
the file clear the avatar instead of stranding it.

The backfill only adopts URLs that name a file which actually exists; any
other legacy value (an arbitrary link from before stage 2.3) becomes NULL and
falls back to the letter avatar. That is deliberate: an unverifiable URL must
not survive into a schema whose whole point is that every picture is read
through a permission check.

Revision ID: c9e5a7d3f8b2
Revises: b48f0a6d1c77
Create Date: 2026-10-09

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9e5a7d3f8b2"
down_revision: str | None = "b48f0a6d1c77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The only legacy shape worth keeping: the link ``filesApi.downloadUrl`` used
#: to build, i.e. one that names one of our own file rows. The uuid pattern is
#: strict enough that the ``::uuid`` cast below cannot fail on a match.
_FILE_URL_PATTERN = (
    r"files/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_file_id", sa.Uuid(), nullable=True))

    op.execute(
        f"""
        UPDATE users u
        SET avatar_file_id = m.file_id::uuid
        FROM (
            SELECT id,
                   (regexp_match(avatar_url, '{_FILE_URL_PATTERN}'))[1] AS file_id
            FROM users
            WHERE avatar_url IS NOT NULL
              AND avatar_url ~ '{_FILE_URL_PATTERN}'
        ) m
        WHERE u.id = m.id
          AND EXISTS (
              SELECT 1 FROM files f
              WHERE f.id = m.file_id::uuid
                AND f.content_type LIKE 'image/%'
          )
        """
    )

    op.create_foreign_key(
        op.f("fk_users_avatar_file_id_files"),
        "users",
        "files",
        ["avatar_file_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_users_avatar_file_id", "users", ["avatar_file_id"], unique=False)
    op.drop_column("users", "avatar_url")


def downgrade() -> None:
    op.add_column("users", sa.Column("avatar_url", sa.String(length=512), nullable=True))
    # Rebuild the old link for every avatar whose file still exists - the
    # reverse of the upgrade's filter, in the exact shape the old frontend
    # produced. Avatars whose file is gone stay NULL either way.
    op.execute(
        """
        UPDATE users u
        SET avatar_url = '/api/v1/files/' || f.id || '?organization_id=' || f.organization_id
        FROM files f
        WHERE f.id = u.avatar_file_id
        """
    )
    op.drop_constraint(op.f("fk_users_avatar_file_id_files"), "users", type_="foreignkey")
    op.drop_index("ix_users_avatar_file_id", table_name="users")
    op.drop_column("users", "avatar_file_id")
