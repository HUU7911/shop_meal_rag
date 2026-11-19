"""Khởi tạo schema: conversations, chat_messages, feedback, ingestion_documents, ingestion_runs.

Revision ID: 0001_init
Revises:

Viết tay để khớp app/db/models/*. Sau khi đổi model, kiểm tra không còn lệch bằng `make migrate-check`
(`alembic check`) rồi tạo migration mới bằng `alembic revision --autogenerate -m "..."`.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def _dt6() -> sa.types.TypeEngine:
    # Khớp app.db.types.UTCDateTime: DATETIME(6) trên MySQL
    return sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("created_at", _dt6(), nullable=False),
        sa.Column("updated_at", _dt6(), nullable=False),
        sa.Column("deleted_at", _dt6(), nullable=True),
    )
    op.create_index("ix_conv_user_updated", "conversations", ["user_id", "updated_at"])
    op.create_index("ix_conv_deleted_at", "conversations", ["deleted_at"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "conversation_id", sa.String(40), sa.ForeignKey("conversations.id"), nullable=False
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(32), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=True),
        sa.Column("trace", sa.JSON(), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("created_at", _dt6(), nullable=False),
    )
    op.create_index("ix_msg_conv_created", "chat_messages", ["conversation_id", "created_at"])

    op.create_table(
        "feedback",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("message_id", sa.String(40), sa.ForeignKey("chat_messages.id"), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("rating", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(32), nullable=True),
        sa.Column("comment", sa.String(1000), nullable=True),
        sa.Column("created_at", _dt6(), nullable=False),
        sa.UniqueConstraint("message_id", "user_id", name="uq_feedback_msg_user"),
    )
    op.create_index("ix_feedback_message_id", "feedback", ["message_id"])

    op.create_table(
        "ingestion_documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("content_type", sa.String(16), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("version", sa.String(32), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("kb_version", sa.String(32), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("content_type", "source_id", name="uq_ing_doc"),
    )
    op.create_index("ix_ing_status", "ingestion_documents", ["status"])

    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("added", sa.Integer(), nullable=False),
        sa.Column("updated", sa.Integer(), nullable=False),
        sa.Column("deleted", sa.Integer(), nullable=False),
        sa.Column("skipped", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ingestion_runs")
    op.drop_index("ix_ing_status", table_name="ingestion_documents")
    op.drop_table("ingestion_documents")
    op.drop_index("ix_feedback_message_id", table_name="feedback")
    op.drop_table("feedback")
    op.drop_index("ix_msg_conv_created", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_conv_deleted_at", table_name="conversations")
    op.drop_index("ix_conv_user_updated", table_name="conversations")
    op.drop_table("conversations")
