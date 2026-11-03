# core/

| File | Nội dung |
|---|---|
| `config.py` | `Settings` (pydantic-settings), tên biến khớp `.env.example`; `mysql_url`, `redis_url` dựng từ biến thành phần |
| `security.py` | `get_current_user` (JWT / header Gateway khi được tin / guest), `require_login` |
| `logging.py` | Log có `request_id`, che token/email/số dài |
| `middleware.py` | `X-Request-ID`, đo thời gian; (TODO) rate limit Redis |
| `exceptions.py` | Hệ thống `AppError` + handler trả `ErrorResponse` |
| `dependencies.py` | DI: DB session, Redis, ChatService, RAGEngine (khởi tạo tài nguyên nặng trong lifespan) |

Không đặt nghiệp vụ chat/RAG ở đây.
