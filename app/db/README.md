# db/

SQLAlchemy 2.0 async + Alembic (`/migrations`). Tạo migration: `alembic revision --autogenerate -m "init"`.

| Bảng | Mục đích |
|---|---|
| `conversations` | `user_id` NULL = khách; `deleted_at` = soft delete |
| `chat_messages` | role, content, intent, `sources` (JSON), `trace` (JSON: chunk+score, model, prompt_version, usage, latency) |
| `feedback` | rating/reason/comment theo `message_id` |
| `ingestion_documents` | Registry: content_hash, version, status → incremental & xóa dữ liệu cũ |
| `ingestion_runs` | Nhật ký mỗi lần chạy ingestion |

Repositories chỉ truy cập DB. Job dọn dẹp theo `HISTORY_RETENTION_DAYS` (purge soft-deleted/cũ) cần được bổ sung.
