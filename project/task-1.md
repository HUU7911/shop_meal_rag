# Member 01 – API, Services, DB, tích hợp

**Mục tiêu:** Dịch vụ FastAPI ổn định, an toàn, có lịch sử hội thoại và tích hợp hệ thống Shop Meal.

## Việc cần làm
1. **Khung & hạ tầng (M0):** `main.py`, middleware request-id, config, exceptions, compose healthcheck, Makefile, CI lint/test.
2. **DB (M1):** hoàn thiện models + repositories, Alembic migration đầu tiên (`conversations`, `chat_messages`, `feedback`, `ingestion_*`).
3. **Services (M1):** `ChatService` (điều phối), `ConversationService` (quyền sở hữu), `HistoryService` (Redis + MySQL, cắt theo token), `FeedbackService`, `HealthService` (ping thật).
4. **API (M1–M3):** `/chat`, `/conversations`, `/history`, `/feedback`, `/health*`, `/admin/ingestion/run`, `/chat/stream` (SSE).
5. **Bảo mật (M3):** `decode_jwt` (public key/JWKS), guest policy, kiểm tra chủ sở hữu, rate limit Redis, CORS, `/admin` bảo vệ.
6. **Integrations (M2–M3):** `ProductClient`, `OrderClient` (timeout, retry, lỗi chuẩn).
7. **Mock:** `MockRAGEngine` ở M0 để làm việc song song với Member 02.

## Không làm
Logic embedding/chunking/truy vấn Qdrant; viết lại câu hỏi; chọn model.

## Bàn giao
- API chạy đúng `docs/CONTRACTS.md` §1; `messageId` luôn có.
- Test: quyền sở hữu conversation, guest bị chặn ORDER_STATUS, giới hạn độ dài/ rate limit.
