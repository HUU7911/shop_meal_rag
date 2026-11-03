# Member 02 – RAG, Embedding, Evaluation

**Mục tiêu:** Pipeline trả lời chính xác, có nguồn, an toàn; chất lượng được đo bằng số.

## Việc cần làm
1. **Embedding (M0–M1):** `EmbeddingService` (dense + sparse), `text_normalizer`; so sánh `bge-m3` vs `multilingual-e5-large` bằng eval.
2. **Retriever (M1–M2):** dense → hybrid (RRF) + filter bắt buộc (`enabled`, `effective_date`, `content_type`); kiểm tra metadata collection khi khởi động.
3. **Reranker (M2):** cross-encoder, `RERANK_TOP_N`, chạy trong threadpool.
4. **Query processing (M2):** viết lại câu hỏi độc lập theo lịch sử + trích bộ lọc (giá, danh mục).
5. **Intent router (M2):** luật + từ khóa trước; đo accuracy trong eval.
6. **Tools (M2–M3):** `product_search`, `product_detail` (live), `order_status` (JWT user).
7. **Context/Prompt/LLM (M1–M2):** `context_builder` (token budget, sources có url), prompt file có version, `llm_service` (timeout/retry/fallback/streaming).
8. **Guardrails (M2):** injection, PII, fallback không-có-context, quy tắc dị ứng/dinh dưỡng.
9. **Evaluation (M1→):** `eval/run_eval.py`, metric theo `eval/README.md`, báo cáo trước/sau mỗi thay đổi.

## Không làm
Đọc/ghi MySQL, xử lý HTTP, ingestion.

## Bàn giao
- `RAGEngine.invoke/stream` đúng `app/rag/types.py`; `trace` đầy đủ (chunk, score, prompt_version, usage, latency).
- Báo cáo eval đạt ngưỡng ở M2.
