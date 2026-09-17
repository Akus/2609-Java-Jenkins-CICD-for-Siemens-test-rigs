"""initial schema: rigs, reservations, status_history

Revision ID: 0001
Revises:
Create Date: 2026-09-17

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rigs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("lab", sa.String(32), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("firmware", sa.String(64), nullable=False),
        sa.Column("temperature_c", sa.Float(), nullable=True),
        sa.Column("last_seen", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(512), nullable=False),
        sa.Column("failure_streak", sa.Integer(), nullable=False),
        sa.Column("quarantined", sa.Boolean(), nullable=False),
        sa.Column("quarantine_reason", sa.String(512), nullable=False),
    )
    op.create_index("ix_rigs_lab", "rigs", ["lab"])
    op.create_index("ix_rigs_state", "rigs", ["state"])
    op.create_index("ix_rigs_quarantined", "rigs", ["quarantined"])

    op.create_table(
        "reservations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("rig_id", sa.String(64), sa.ForeignKey("rigs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner", sa.String(128), nullable=False),
        sa.Column("reserved_at", sa.DateTime(), nullable=False),
        sa.Column("ttl_s", sa.Integer(), nullable=False),
        sa.Column("released_at", sa.DateTime(), nullable=True),
        sa.Column("release_reason", sa.String(64), nullable=False),
    )
    op.create_index("ix_reservations_rig_id", "reservations", ["rig_id"])
    op.create_index("ix_reservations_released_at", "reservations", ["released_at"])

    op.create_table(
        "status_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("rig_id", sa.String(64), sa.ForeignKey("rigs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("firmware", sa.String(64), nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_status_history_rig_id", "status_history", ["rig_id"])
    op.create_index("ix_status_history_ts", "status_history", ["ts"])


def downgrade() -> None:
    op.drop_table("status_history")
    op.drop_table("reservations")
    op.drop_table("rigs")
