Test tích hợp (đánh dấu `@pytest.mark.integration`) cần Qdrant/MySQL/Redis chạy bằng docker compose.
Gợi ý: ingestion end-to-end trên `data/` mẫu; chat end-to-end với LLM giả (mock); kiểm tra filter
`enabled`/`effective_date`; kiểm tra quyền sở hữu conversation.
