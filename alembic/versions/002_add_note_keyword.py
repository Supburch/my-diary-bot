"""add note keyword column

Revision ID: 002
Revises: 001
Create Date: 2026-08-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # idempotent — ข้ามถ้าคอลัมน์มีอยู่แล้ว (เช่น create_all สร้างไว้ก่อน)
    columns = [c["name"] for c in inspector.get_columns("diary_entries")]
    if "keyword" not in columns:
        op.add_column(
            "diary_entries",
            sa.Column("keyword", sa.String(length=255), nullable=True),
        )
        op.create_index("ix_diary_entries_keyword", "diary_entries", ["keyword"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    indexes = {i["name"] for i in inspector.get_indexes("diary_entries")}
    if "ix_diary_entries_keyword" in indexes:
        op.drop_index("ix_diary_entries_keyword", table_name="diary_entries")

    columns = [c["name"] for c in inspector.get_columns("diary_entries")]
    if "keyword" in columns:
        op.drop_column("diary_entries", "keyword")
