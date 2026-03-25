"""Initial schema: ChatMessage and SessionHistory tables

Revision ID: 0001
Revises:
Create Date: 2026-03-25

This is the baseline migration. It creates the two tables that the app needs.
All future schema changes (adding columns, indexes, etc.) will be new migration
files that reference this one as their base.
"""
from alembic import op
import sqlalchemy as sa

# Revision identifiers used by Alembic to track which migrations have been applied
revision = "0001"
down_revision = None  # None means this is the first migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create ChatMessage and SessionHistory tables."""

    op.create_table(
        "chatmessage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("source_agent", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chatmessage_session_id", "chatmessage", ["session_id"])

    op.create_table(
        "sessionhistory",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index("ix_sessionhistory_user_id", "sessionhistory", ["user_id"])


def downgrade() -> None:
    """Drop both tables — reverses the upgrade() exactly."""
    op.drop_index("ix_sessionhistory_user_id", table_name="sessionhistory")
    op.drop_table("sessionhistory")
    op.drop_index("ix_chatmessage_session_id", table_name="chatmessage")
    op.drop_table("chatmessage")
