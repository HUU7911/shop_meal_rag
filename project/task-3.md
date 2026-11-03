# Member 03 – Ingestion, Data, Golden set

**Mục tiêu:** Knowledge Base sạch, cập nhật được, truy vết được; có bộ câu hỏi chuẩn để đo.

## Việc cần làm
1. **Dữ liệu (M0–M1):** thay mẫu bằng FAQ/chính sách thật (`data/faq`, `data/policies`) theo định dạng ở `data/README.md`; policy có `version`, `effective_date`, `enabled`.
2. **Loaders (M1):** `faq_loader`, `policy_loader` (front-matter), `product_loader` (qua `ProductClient`), `document_loader`.
3. **Cleaner & chunking (M1):** theo chiến lược từng loại ở `chunking.py`; không đưa giá/trạng thái vào text embed.
4. **Indexing (M1–M3):** collection versioned + alias, payload index, upsert idempotent (`point_id` uuid5), xóa theo tài liệu.
5. **Registry & incremental (M3):** `ingestion_documents`/`ingestion_runs`, ADD/UPDATE/SKIP/DELETE theo `content_hash`.
6. **CLI & vận hành (M1–M3):** `full|incremental|verify`, log số liệu mỗi lần chạy; (sau) Kafka consumer.
7. **Golden set (M1→):** 50–100 câu trong `eval/golden_set.jsonl` cùng nghiệp vụ và Member 02.

## Không làm
Logic retrieval/generation; gọi Product Service trực tiếp (dùng `integrations`).

## Bàn giao
- `python -m app.ingestion.cli full` chạy lặp lại không tạo trùng; `verify` báo đúng số chunk/metadata.
- Payload đúng `docs/CONTRACTS.md` §3.
