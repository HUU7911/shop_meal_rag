# app/

| Package | Trách nhiệm | Chủ sở hữu |
|---|---|---|
| `api/v1` | Router HTTP, validate, gọi `ChatService` | Member 01 |
| `core` | config, security, logging, exceptions, middleware, dependencies | Member 01 |
| `schemas` | Hợp đồng request/response (camelCase ngoài, snake_case trong) | Member 01 |
| `services` | ChatService (điều phối), Conversation, History, Feedback, Health | Member 01 |
| `db` | SQLAlchemy models + repositories (+ Alembic ở `/migrations`) | Member 01 |
| `integrations` | Client Product/Order Service (dùng chung) | Member 01 (hợp đồng), Member 02/03 dùng |
| `embedding` | EmbeddingService + chuẩn hóa text, dùng chung | Member 02 |
| `rag` | Pipeline RAG, tools, guardrails, prompts | Member 02 |
| `ingestion` | Nạp tri thức vào Qdrant | Member 03 |

Quy tắc phụ thuộc: xem `docs/ARCHITECTURE.md` §3. Hợp đồng giữa các package: `docs/CONTRACTS.md`.
