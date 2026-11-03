# Shop Meal RAG Chatbot

Chatbot AI hỏi đáp cho hệ thống Shop Meal (microservices), xây dựng theo kiến trúc
**Retrieval-Augmented Generation** với FastAPI, Qdrant, Redis, MySQL.

> Đây là **phiên bản cấu trúc v2** (đã rà soát và bổ sung so với v1). Xem
> [`docs/MIGRATION_FROM_V1.md`](docs/MIGRATION_FROM_V1.md) để biết những gì đã thay đổi.

## Chatbot trả lời được gì

| Loại câu hỏi | Ví dụ | Cách xử lý |
|---|---|---|
| FAQ / Chính sách | "Có được hủy đơn không?" | RAG trên Qdrant (hybrid + rerank) |
| Tìm sản phẩm | "Món cơm dưới 50k?" | Tool `product_search` + lọc metadata, **giá/trạng thái lấy live** |
| Chi tiết sản phẩm | "Cơm gà xối mỡ còn hàng không?" | Gọi Product Service trực tiếp |
| Đơn hàng của tôi | "Đơn #123 đang ở đâu?" | Gọi Order Service bằng JWT của user (cần đăng nhập) |
| Ngoài phạm vi / chào hỏi | "Thời tiết hôm nay?" | Từ chối lịch sự / trả lời ngắn, không truy xuất |

## Cấu trúc thư mục

```text
shop_meal_rag/
├── app/
│   ├── main.py              # FastAPI app factory
│   ├── api/v1/              # Router: chat, conversations, history, feedback, health, admin
│   ├── core/                # config, security, logging, exceptions, middleware, dependencies
│   ├── schemas/             # Pydantic request/response (hợp đồng API)
│   ├── services/            # ChatService, ConversationService, HistoryService, FeedbackService, HealthService
│   ├── integrations/        # Client gọi Product/Order Service (dùng chung cho services + ingestion)
│   ├── db/                  # SQLAlchemy: base, session, models/, repositories/
│   ├── embedding/           # EmbeddingService DÙNG CHUNG cho rag và ingestion
│   ├── rag/                 # router(intent), query_processor, retriever, reranker, context_builder,
│   │   ├── prompts/         #   prompt_builder, guardrails, llm_service, rag_engine
│   │   └── tools/           #   product_search, product_detail, order_status
│   └── ingestion/           # loaders/, cleaner, chunking, indexing, registry, cli
├── data/                    # faq/, policies/, products/, documents/, processed/
├── eval/                    # golden set + script đánh giá RAG
├── tests/                   # unit/ + integration/
├── migrations/              # Alembic
├── docs/                    # ARCHITECTURE, CONTRACTS, DECISIONS, SECURITY, MIGRATION_FROM_V1
├── project/                 # Phân công, tiến độ, task từng thành viên
├── scripts/                 # Script tiện ích
├── Dockerfile  docker-compose.yaml  Makefile  pyproject.toml  requirements*.txt  .env.example
```

## Chạy nhanh

```bash
cp .env.example .env          # đổi toàn bộ mật khẩu / key
docker compose up -d --build  # qdrant + redis + mysql + chatbot
docker compose exec chatbot alembic upgrade head
docker compose --profile ingest run --rm ingestion      # nạp tri thức lần đầu
curl http://localhost:8000/api/v1/chatbot/health
```

Phát triển cục bộ: `make install && make dev` (cần Qdrant/Redis/MySQL chạy bằng compose).

## Đọc theo thứ tự

1. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) – luồng xử lý và thành phần.
2. [`docs/CONTRACTS.md`](docs/CONTRACTS.md) – **hợp đồng giữa 3 thành viên** (đọc trước khi code).
3. [`docs/DECISIONS.md`](docs/DECISIONS.md) – các quyết định thiết kế và lý do.
4. [`docs/SECURITY.md`](docs/SECURITY.md) – bảo mật và guardrails.
5. [`project/manager.md`](project/manager.md) – phân công và mốc tiến độ.
