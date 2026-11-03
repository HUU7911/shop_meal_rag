# services/

`ChatService` là nơi duy nhất điều phối một lượt chat (xem docstring trong file).
Quy tắc: không logic embedding/chunking/truy vấn Qdrant; không gọi HTTP service ngoài trực tiếp
(dùng `integrations/`); dữ liệu chỉ đi qua `db/repositories`.

| Service | Việc |
|---|---|
| `ChatService` | Điều phối: conversation → history → `RAGEngine` → lưu → response |
| `ConversationService` | Tạo/kiểm tra quyền sở hữu/soft delete |
| `HistoryService` | Redis cache + MySQL; cắt theo token budget; lưu sources & trace |
| `FeedbackService` | Lưu và thống kê feedback |
| `HealthService` | Ping Qdrant/Redis/MySQL cho `/health/ready` |
