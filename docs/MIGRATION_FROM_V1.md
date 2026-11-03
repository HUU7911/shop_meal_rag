# So sánh v1 → v2

## Lỗi/mâu thuẫn đã sửa
| v1 | v2 |
|---|---|
| Thiếu `app/rag/`, `main.py`, `requirements.txt` | Có đầy đủ (stub + hợp đồng) |
| `dockerfile` vs `Dockerfile` trong compose | Thống nhất `Dockerfile` |
| Tên biến `.env` lệch `core/README` | Một bộ biến duy nhất, `config.py` khớp `.env.example` |
| Ingestion: 3 file vs 6 file, tên file FAQ/policy mỗi nơi một kiểu | Một cấu trúc (`ingestion/` ở README mới) |
| `data/products`, `documents`, `processed` chỉ có trong mô tả | Tạo sẵn thư mục |
| API gọi ConversationService vs ChatService | Chỉ `ChatService` |
| `ChatResponse` thiếu `messageId` | Có `messageId` |
| Task có Conversation API nhưng `api/` không có | Thêm `conversations.py` |
| `REAME.md` ×3 | `README.md` |

## Bổ sung mới
- `rag/`: IntentRouter, QueryProcessor (rewrite + filter), Reranker, Guardrails, tools sản phẩm/đơn hàng.
- `embedding/` dùng chung; `integrations/` dùng chung (thay `product_service` ở services).
- `db/` (models, repositories) + Alembic; bảng `ingestion_documents`, `ingestion_runs`.
- Ingestion: `cleaner`, `chunking` theo loại dữ liệu, `registry`, `cli`, `events` (Kafka tùy chọn).
- `eval/` (golden set + script), `tests/`, `Makefile`, `pyproject.toml`, CI-ready.
- Docker: ghim version, healthcheck đủ, mật khẩu Redis/Qdrant, bind localhost, non-root, service `ingestion`.
- `docs/` (kiến trúc, hợp đồng, quyết định, bảo mật), `project/` có mốc tiến độ và người sở hữu eval/DevOps.

## Việc không đổi
Stack (FastAPI, Qdrant, Redis, MySQL, Pydantic), 3 vai trò Member 01/02/03, tích hợp Spring Cloud Gateway + JWT.
