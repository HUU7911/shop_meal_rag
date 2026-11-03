# Bảo mật và Guardrails

## Hạ tầng
- Qdrant có API key; Redis có mật khẩu; MySQL dùng user riêng (không dùng root cho app).
- Cổng hạ tầng chỉ bind `127.0.0.1` trong compose. Production: không publish, dùng mạng nội bộ.
- Ghim version image (không `:latest`). Container chạy non-root.
- Secret chỉ qua env / secret manager; `.env` không commit.

## Xác thực & phân quyền
- Xác thực JWT (public key hoặc JWKS). `sub` → `user_id`.
- Chỉ tin header user-id từ Gateway khi `TRUST_GATEWAY_USER_HEADER=true` **và** chatbot không public trực tiếp.
- Guest (`ALLOW_GUEST=true`): chỉ FAQ/chính sách/sản phẩm; tool `order_status` yêu cầu đăng nhập.
- Mọi truy cập conversation/history kiểm tra **chủ sở hữu**.
- Endpoint `/admin/*`: `X-Internal-Key` hoặc role ADMIN.
- Rate limit theo user/IP (`RATE_LIMIT_PER_MINUTE`) + ngân sách token LLM theo ngày.
- CORS chỉ cho origin trong `CORS_ORIGINS`.

## Guardrails (app/rag/guardrails.py)
**Đầu vào:** giới hạn độ dài; phát hiện prompt injection thô (ví dụ yêu cầu bỏ qua chỉ dẫn, lộ system prompt);
che PII (SĐT, email, số thẻ) trước khi log.

**Nội dung truy xuất:** coi tài liệu/mô tả sản phẩm là **dữ liệu không đáng tin**; prompt bọc trong thẻ
`<context>` và yêu cầu LLM không làm theo chỉ dẫn nằm trong context.

**Đầu ra:**
- Chỉ trả lời dựa trên context/tool; không có thông tin → fallback + handoff, không suy đoán.
- Mỗi câu trả lời dựa trên RAG phải kèm `sources`.
- Giá/trạng thái chỉ lấy từ tool live; nếu tool lỗi thì nói rõ không kiểm tra được.
- **Dị ứng/dinh dưỡng/y tế:** chỉ nêu khi có trong dữ liệu; luôn kèm lưu ý kiểm tra lại với cửa hàng.
  Không khẳng định "không chứa X" nếu dữ liệu không nói rõ.
- Không tiết lộ system prompt, cấu hình, dữ liệu người dùng khác.

## Dữ liệu cá nhân
- Không đưa PII vào Knowledge Base.
- Lịch sử lưu theo `HISTORY_RETENTION_DAYS`; hỗ trợ xóa theo yêu cầu người dùng (soft delete → purge job).
- Log không chứa token/API key/nội dung PII chưa che.
