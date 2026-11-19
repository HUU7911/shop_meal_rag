# Báo cáo Member 01 – đánh giá và hoàn thiện

Phạm vi theo `project/task-1.md`: `api/`, `core/`, `schemas/`, `services/`, `db/`, `migrations/`, `integrations/`,
Docker/compose, CI, rate limit, JWT, `MockRAGEngine`.

## 1. Đánh giá hiện trạng (trước khi làm)

Khung dự án (hợp đồng, schema, model, cấu hình) tốt. Phần thực thi của Member 01 **chưa chạy được**:
mọi endpoint (trừ `/health`) và mọi service ném `NotImplementedError`, hai client trả `NotImplementedError`,
`migrations/versions/` rỗng, không có CI, không có test cho phần này.

Lỗi/rủi ro tìm thấy trong code có sẵn (đã sửa):

| # | Vấn đề | Hậu quả | Cách xử lý |
|---|---|---|---|
| 1 | `DATETIME` MySQL chỉ tới giây | message user/assistant cùng giây → thứ tự lịch sử không xác định | `DATETIME(6)`, thời điểm đặt từ Python, assistant luôn sau user |
| 2 | Không có chỗ nào `commit` (`get_db_session` chỉ `yield`) | dữ liệu không bao giờ được lưu | Unit of Work: commit khi thoát khối, rollback khi lỗi; bỏ `get_db_session` |
| 3 | `conversations.updated_at` chỉ cập nhật khi chính dòng đó bị UPDATE | danh sách conversation không sắp theo hoạt động | `touch()` mỗi lượt |
| 4 | `BaseHTTPMiddleware` | SSE bị ảnh hưởng, đo thời gian sai với stream | middleware ASGI thuần |
| 5 | `exc_info=True` ngoài khối `except` | log lỗi 5xx chỉ in `NoneType: None` | `exc_info=exc` |
| 6 | Không handler cho `RequestValidationError` / `HTTPException` | 422/404/405 sai dạng lỗi chuẩn trong hợp đồng; 422 mặc định còn lặp lại input người dùng | handler chuẩn, không lặp input |
| 7 | So khớp `X-Internal-Key` bằng `==` | timing attack | `hmac.compare_digest` |
| 8 | `CurrentUser` là dataclass có `token` trong `repr` | lộ JWT khi log đối tượng | `repr=False` |
| 9 | Không `Retry-After`, không `ConflictError` | 429/409 thiếu chuẩn | `AppError.headers`, `ConflictError` |
| 10 | Feedback không ràng buộc duy nhất | một user gửi nhiều feedback cho một câu trả lời | unique `(message_id, user_id)`, gửi lại = cập nhật |
| 11 | Id đưa thẳng vào URL của Product/Order Service | path traversal / SSRF cục bộ | kiểm tra ký tự trước khi gọi |
| 12 | Message chỉ gồm khoảng trắng hợp lệ; `conversationId` không giới hạn độ dài | rác trong DB, lỗi cột `String(40)` | validator trong schema |
| 13 | compose publish `8000` ra mọi interface; chatbot khởi động trước migration | lộ dịch vụ; lần chạy đầu lỗi bảng không tồn tại | bind `127.0.0.1`, thêm service `migrate` |
| 14 | `.env.example` thiếu `RAG_ENABLED`, `LLM_ENABLED`, `RERANK_*`… đang có trong `Settings` | không ai biết cách bật RAG thật | bổ sung (không thêm biến mới) |

## 2. Đã làm

* **core**: handler lỗi chuẩn, middleware request-id, rate limit Redis (fail-open, `Retry-After`), DI qua `app.state.services`,
  kiểm tra cấu hình production, ẩn `/docs` ở production, CORS an toàn.
* **db**: Unit of Work, repository đầy đủ, migration `0001_init`, job purge theo retention (`make purge`).
* **services**: `ChatService` (JSON + SSE, không giữ transaction trong lúc gọi LLM, chặn khách xem đơn hàng ở lớp thứ hai),
  `ConversationService`, `HistoryService` (cache Redis + cắt theo token budget), `FeedbackService`, `HealthService`
  (ping thật), `IngestionService` (nền, 409 nếu đang chạy, tiến trình con), `MockRAGEngine`.
* **api**: toàn bộ endpoint theo `docs/CONTRACTS.md`, thêm `GET /admin/ingestion/runs/{id}`.
* **integrations**: `ProductClient`, `OrderClient` (timeout, retry GET, ánh xạ trường linh hoạt, lỗi chuẩn).
* **hạ tầng**: service `migrate` trong compose, CI GitHub Actions, `make migrate-check`.
* **tài liệu**: `CONTRACTS.md` (SSE, phân trang, mã lỗi, health, giả định upstream), `DECISIONS.md` (#18–24).

## 3. Chưa kiểm chứng / cần làm khi có môi trường đầy đủ

Môi trường làm việc **không có mạng và không có fastapi/pydantic/sqlalchemy/pytest**, nên:

* Đã chạy được thật: `test_history_trim`, `test_rate_limit`, `test_integrations` (22 test; riêng `test_integrations`
  chạy với shim `httpx` tối thiểu, không phải httpx thật) và kiểm tra cú pháp + tên chưa định nghĩa/import thừa cho toàn bộ file.
* **Chưa chạy**: `test_api_*`, `test_history_service`, `test_services_misc`, `test_security` (cần FastAPI/pydantic/PyJWT…),
  migration trên MySQL thật, `docker compose up`, `ruff`, `mypy`.
  Việc đầu tiên: `pytest -m "not integration"`, `make migrate && make migrate-check`, `docker compose up --build`.
* `make migrate-check` (`alembic check`) phải sạch; nếu lệch, sửa `0001_init.py` cho khớp model.

## 4. Việc còn mở (cần người khác hoặc quyết định)

1. **Xác nhận API Product/Order Service** (đường dẫn, dạng phân trang, endpoint "đơn của tôi") – xem giả định trong `CONTRACTS.md` §5.
2. **Ngân sách token LLM theo ngày** (`SECURITY.md`) chưa làm: cần biến môi trường mới, mâu thuẫn quy tắc "không thêm biến".
3. **Lint toàn repo**: job `lint` trong CI đang `continue-on-error` vì chưa chạy được ruff/mypy trên code của Member 02/03
   (có ít nhất một import thừa ở `app/ingestion/loaders/product_loader.py`). Dọn xong thì bỏ `continue-on-error`.
4. **Member 02**: `OrderClient` ném `AuthenticationError` khi token hết hạn, nhưng tool `order_status` bắt mọi `Exception` và
   báo "không kiểm tra được" – người dùng không biết cần đăng nhập lại. Nên bắt riêng `AuthenticationError`.
   `RETRIEVAL_SCORE_THRESHOLD` mặc định trong `config.py` (0.05) khác `.env.example` (0.35).
5. **Member 03**: `ingestion/registry.py` dùng `datetime.now(timezone.utc)` (aware) cho cột `DateTime` không múi giờ;
   `pipeline.run()` chưa dùng registry nên `ingestion_runs` hiện do API ghi; khi Member 03 thêm `start_run` vào pipeline cần tránh tạo trùng.
6. Khách giữ `conversationId` như bí mật (id ngẫu nhiên 128 bit); ai biết id đó có thể tiếp tục hội thoại của khách. Chấp nhận được cho MVP.
7. Lượt chat bị ngắt giữa chừng khi stream không được lưu (đã ghi trong hợp đồng).
