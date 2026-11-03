# api/

Chỉ làm: nhận request, xác thực (`get_current_user`), validate, gọi **`ChatService`**, trả response.
Không: gọi RAG/LLM/Qdrant trực tiếp, chứa nghiệp vụ, viết SQL.

| File | Endpoint |
|---|---|
| `v1/chat.py` | `POST /chat`, `POST /chat/stream` (SSE) |
| `v1/conversations.py` | `POST/GET /conversations` |
| `v1/history.py` | `GET/DELETE /history/{conversation_id}` |
| `v1/feedback.py` | `POST /feedback` |
| `v1/health.py` | `GET /health` (liveness), `GET /health/ready` |
| `v1/admin.py` | `POST /admin/ingestion/run` (ADMIN / `X-Internal-Key`) |

Chi tiết hợp đồng: `docs/CONTRACTS.md` §1. Lỗi trả theo `ErrorResponse`.
