"""Đăng ký/đăng nhập: bảng users và refresh_tokens.

Revision ID: 0002_auth
Revises: 0001_init
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0002_auth"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def _dt6() -> sa.types.TypeEngine:
    return sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")     # khớp app.db.types.UTCDateTime


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(100), nullable=True),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), nullable=False),
        sa.Column("locked_until", _dt6(), nullable=True),
        sa.Column("last_login_at", _dt6(), nullable=True),
        sa.Column("password_changed_at", _dt6(), nullable=True),
        sa.Column("created_at", _dt6(), nullable=False),
        sa.Column("updated_at", _dt6(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("user_id", sa.String(40), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("family_id", sa.String(40), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", _dt6(), nullable=False),
        sa.Column("expires_at", _dt6(), nullable=False),
        sa.Column("revoked_at", _dt6(), nullable=True),
        sa.Column("replaced_by", sa.String(40), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_refresh_token_hash"),
    )
    op.create_index("ix_refresh_user", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_family", "refresh_tokens", ["family_id"])


def downgrade() -> None:
    op.drop_index("ix_refresh_family", table_name="refresh_tokens")
    op.drop_index("ix_refresh_user", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")