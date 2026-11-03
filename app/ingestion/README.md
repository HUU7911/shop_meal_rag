# ingestion/

Nạp tri thức vào Qdrant. Chạy bằng CLI (`python -m app.ingestion.cli full|incremental|verify`) hoặc cron;
Kafka (`events.py`) để giai đoạn sau.

| File | Việc |
|---|---|
| `loaders/` | `faq_loader` (JSON), `policy_loader` (Markdown + front-matter), `product_loader` (qua `integrations`), `document_loader` |
| `cleaner.py` | Làm sạch, chuẩn hóa, bỏ trùng/rỗng |
| `chunking.py` | Chunk theo loại (xem docstring) |
| `payload.py` | **Hợp đồng payload** + `point_id` (uuid5) + `content_hash` + danh sách field cần index |
| `indexing.py` | Collection versioned + alias, payload index, upsert, xóa |
| `registry.py` | Incremental: ADD/UPDATE/SKIP/DELETE dựa trên hash |
| `pipeline.py` | load → clean → plan → chunk → embed → upsert → run log |

Nguyên tắc: idempotent; một tài liệu lỗi không làm hỏng cả job; không đưa giá/trạng thái vào text embed;
không chứa logic retrieval/generation; dữ liệu nguồn đã `enabled=false` hoặc hết hiệu lực thì xóa/ẩn khỏi KB.
