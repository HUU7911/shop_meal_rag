# embedding/

`EmbeddingService` duy nhất cho cả query (`rag`) và document (`ingestion`) → đảm bảo cùng model/chuẩn hóa.
- Chọn model bằng `eval/` (ứng viên: `BAAI/bge-m3`, `intfloat/multilingual-e5-large`).
- Sinh cả dense và sparse để hỗ trợ hybrid.
- Chạy trong threadpool khi gọi từ code async; nạp model một lần ở lifespan.
- Model name/dim được ghi vào metadata collection; `rag` kiểm tra khớp khi khởi động.
