"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-08-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if "diary_entries" not in existing:
        op.create_table(
            "diary_entries",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column("entry_date", sa.Date(), nullable=False),
            sa.Column("code", sa.String(length=32), nullable=False),
            sa.Column("category", sa.String(length=255), nullable=False),
            sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("count", sa.Integer(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_diary_entries_user_id", "diary_entries", ["user_id"])
        op.create_index("ix_diary_entries_entry_date", "diary_entries", ["entry_date"])

    if "user_habits" not in existing:
        op.create_table(
            "user_habits",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column("code", sa.String(length=2), nullable=False),
            sa.Column("category", sa.String(length=255), nullable=False),
            sa.Column("icon", sa.String(length=10), nullable=False, server_default="▪"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_user_habits_user_id", "user_habits", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_habits_user_id", table_name="user_habits")
    op.drop_table("user_habits")
    op.drop_index("ix_diary_entries_entry_date", table_name="diary_entries")
    op.drop_index("ix_diary_entries_user_id", table_name="diary_entries")
    op.drop_table("diary_entries")
