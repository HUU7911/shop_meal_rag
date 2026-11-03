# Phân công và tiến độ

## Vai trò

| Thành viên | Phạm vi chính | Cũng sở hữu |
|---|---|---|
| **Member 01** | `api`, `core`, `schemas`, `services`, `db`, Alembic, `integrations` (hợp đồng + client) | Docker/compose, CI (lint+test), tích hợp Gateway/JWT, rate limit |
| **Member 02** | `rag`, `embedding` | **Evaluation** (`eval/run_eval.py`, báo cáo), chọn embedding/rerank bằng số đo |
| **Member 03** | `ingestion`, `data` | **Golden set** (cùng nghiệp vụ), chất lượng dữ liệu, registry, chiến lược chunk |

## Hợp đồng (làm TRƯỚC khi code – Mốc 0)
- [ ] Duyệt `docs/CONTRACTS.md` (API, `RAGResult`, payload Qdrant, `EmbeddingService`, integrations).
- [ ] Member 01 dựng **MockRAGEngine** (trả `RAGResult` giả) để không bị chặn bởi Member 02.
- [ ] Member 02 + 03 thống nhất model embedding tạm thời và `EMBEDDING_DIM`.
- [ ] Chốt bộ biến `.env.example` (không tự thêm biến mới ngoài tài liệu).

## Mốc (đơn vị: tuần, điều chỉnh theo thực tế)

| Mốc | Nội dung | Tiêu chí hoàn thành |
|---|---|---|
| **M0** (tuần 0) | Hợp đồng + khung repo + `docker compose up` chạy | `/health` OK; test hợp đồng pass |
| **M1** (tuần 1–2) | Chat chạy end-to-end với **FAQ + chính sách**: ingestion full, retriever dense, LLM, lưu lịch sử | Hỏi được FAQ; message có `sources`; `make eval` chạy lần đầu (baseline) |
| **M2** (tuần 3–4) | Intent router, tools sản phẩm (live), hybrid + rerank, query rewrite, guardrails, feedback | Hit@4 và intent accuracy đạt ngưỡng ở `eval/README.md`; không còn trả giá cũ |
| **M3** (tuần 5) | Tool đơn hàng + auth, SSE streaming, rate limit, cache, incremental ingestion + registry | Guest bị chặn xem đơn; reindex bằng alias không downtime |
| **M4** (tuần 6) | Hardening: bảo mật compose, observability (trace, latency), test tích hợp, tài liệu vận hành | Checklist bên dưới đạt |

## Checklist "xong" cho mỗi PR
- Đổi chunking/embedding/prompt/retrieval ⇒ đính kèm kết quả `make eval` trước/sau.
- `make lint` và `make test` pass.
- Thay đổi hợp đồng ⇒ cập nhật `docs/CONTRACTS.md` và báo cả nhóm.
- Không commit `.env`, dữ liệu thật, khóa bí mật.

## Rủi ro cần theo dõi
- Chất lượng tiếng Việt của embedding/rerank (giảm rủi ro bằng eval sớm ở M1).
- Độ trễ (embedding + rerank + LLM): đo từng bước, cân nhắc cache/streaming.
- Dữ liệu nghiệp vụ thật chậm về → golden set và KB mẫu phải thay sớm.
- Phụ thuộc Product/Order Service (API chưa chốt): dùng client + mock để không bị chặn.
