# schemas/

Pydantic model của API. Ngoài API dùng **camelCase** (`CamelModel`), trong code dùng snake_case.
`ChatResponse` luôn có `message_id`. `Intent`, `SourceType`, `SourceItem` dùng chung với `rag.types`.
Không đặt model DB hoặc logic nghiệp vụ ở đây.
