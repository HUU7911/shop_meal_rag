from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestIdMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    # TODO: khởi tạo engine MySQL, Redis, Qdrant client, EmbeddingService, Reranker, RAGEngine
    #       -> gắn vào app.state; đóng ở phần sau yield.
    app.state.rag_engine = None
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Shop Meal RAG Chatbot", version="0.1.0", lifespan=lifespan,
                  openapi_url=f"{settings.api_prefix}/openapi.json",
                  docs_url=f"{settings.api_prefix}/docs")
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list,
                       allow_methods=["*"], allow_headers=["*"], allow_credentials=True)
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
