from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestIdMiddleware
from app.db.session import create_engine_and_sessionmaker


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)

    db_engine, db_sessionmaker = create_engine_and_sessionmaker()
    app.state.db_engine = db_engine
    app.state.db_sessionmaker = db_sessionmaker
    app.state.rag_engine = None

    close_rag = None
    try:
        if settings.rag_enabled:
            from app.integrations.order_client import OrderClient
            from app.integrations.product_client import ProductClient
            from app.rag.factory import build_rag_engine

            app.state.rag_engine, close_rag = await build_rag_engine(
                settings, ProductClient(), OrderClient()
            )

        yield
    finally:
        if close_rag:
            await close_rag()
        await db_engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Shop Meal RAG Chatbot",
        version="0.1.0",
        lifespan=lifespan,
        openapi_url=f"{settings.api_prefix}/openapi.json",
        docs_url=f"{settings.api_prefix}/docs",
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
