"""Dependency Injection. Khởi tạo tài nguyên nặng một lần trong lifespan (app.state)."""
from fastapi import Request

# TODO(Member 01): cung cấp
#   - get_db_session()        (AsyncSession)
#   - get_redis()
#   - get_chat_service()      (ghép ChatService với các repository + RAGEngine)
# TODO(Member 02): RAGEngine, EmbeddingService, Reranker được tạo trong lifespan và gắn vào app.state.


def get_rag_engine(request: Request):
    return request.app.state.rag_engine
