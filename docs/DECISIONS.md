# Quyết định thiết kế (ADR rút gọn)

| # | Quyết định | Lý do |
|---|---|---|
| 1 | Router chỉ gọi `ChatService` | Một điểm điều phối duy nhất; tránh mâu thuẫn "API → ConversationService → RAG" của v1 |
| 2 | Thêm **Intent Router** và **tools** (product/order) | Giá, tồn kho, đơn hàng cá nhân không thể trả lời đúng bằng vector search; câu hỏi liệt kê ("có những món nào") cần search có phân trang |
| 3 | **Giá/trạng thái luôn lấy live** | Dữ liệu đã index sẽ cũ; chỉ giữ snapshot để lọc thô |
| 4 | Hybrid (dense + sparse) + reranker nằm trong **MVP** | Tên món/từ khóa tiếng Việt cần khớp từ khóa; đề xuất tăng độ chính xác rõ rệt |
| 5 | Chọn embedding model bằng **eval**, không chọn theo cảm tính | Ứng viên: `BAAI/bge-m3`, `intfloat/multilingual-e5-large`; so Hit@K/MRR trên golden set |
| 6 | `embedding/` là package dùng chung | Tránh lệch model giữa index và query |
| 7 | Alias collection + `kb_version` | Đổi model/schema không downtime |
| 8 | ID điểm = uuid5 từ khóa ổn định + `content_hash` | Upsert idempotent, incremental indexing, xóa được dữ liệu cũ |
| 9 | Registry ingestion trong MySQL (`ingestion_documents`, `ingestion_runs`) | Biết tài liệu nào đã index/đã xóa/phiên bản nào |
| 10 | LangChain chỉ dùng `langchain-text-splitters` | Tự viết retriever/engine để kiểm soát; tránh hai lớp trừu tượng chồng nhau |
| 11 | Ingestion chạy bằng CLI + cron trước, Kafka để sau | Giảm phạm vi MVP; Kafka vẫn có chỗ cắm (`ingestion/events.py`) |
| 12 | Alembic cho migration | v1 có SQLAlchemy nhưng không có cơ chế migrate |
| 13 | SSE streaming thiết kế ngay trong contract | Đổi sau sẽ ảnh hưởng frontend |
| 14 | Lưu `trace` (chunk, score, prompt_version) cùng message | Feedback tiêu cực phải truy ngược được nguyên nhân |
| 15 | Guest được hỏi FAQ/chính sách/sản phẩm; **đơn hàng cần đăng nhập** | Cân bằng trải nghiệm và bảo vệ dữ liệu cá nhân |
| 16 | Prompt tách thành file (`app/rag/prompts/*.md`) có version | Dễ review, A/B, truy vết |
| 17 | Eval là deliverable bắt buộc (`eval/`) | Không có số đo thì không biết thay đổi tốt hay xấu |
