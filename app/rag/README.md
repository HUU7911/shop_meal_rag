# rag/

Pipeline: `guardrails(in) → query_processor → intent_router → [retriever → reranker | tools] → context_builder → prompt_builder → llm_service → guardrails(out)`.

| File | Việc |
|---|---|
| `types.py` | **Hợp đồng** `RAGRequest/RAGResult/RAGTrace/RAGEngine` |
| `rag_engine.py` | Điều phối pipeline, đo latency từng bước |
| `query_processor.py` | Viết lại câu hỏi độc lập theo lịch sử + trích bộ lọc (giá, danh mục) |
| `intent_router.py` | Phân loại ý định (luật → classifier) |
| `retriever.py` | Hybrid Qdrant + filter `enabled`/`effective_date`/`content_type` |
| `reranker.py` | Cross-encoder |
| `context_builder.py` | Ghép context trong token budget + tạo `SourceItem` |
| `prompt_builder.py`, `prompts/` | Prompt tách file, có version |
| `llm_service.py` | Adapter LLM: timeout, retry, fallback, streaming |
| `guardrails.py` | Bảo vệ vào/ra (xem `docs/SECURITY.md`) |
| `tools/` | `product_search`, `product_detail`, `order_status` (dữ liệu live) |

Quy tắc: không HTTP, không MySQL. Giá/trạng thái/đơn hàng chỉ lấy qua tools. Mọi thay đổi chất lượng phải có kết quả `make eval`.
