"""Dựng app FastAPI thật (router, middleware, handler lỗi, JWT) nhưng thay DB/Redis/RAG bằng bản giả.
Không chạy lifespan (không cần MySQL/Redis/Qdrant)."""
import time

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.rate_limit import RateLimiter
from app.services.chat_service import ChatService
from app.services.container import Services
from app.services.conversation_service import ConversationService
from app.services.feedback_service import FeedbackService
from app.services.health_service import HealthService
from app.services.history_service import HistoryService
from app.services.ingestion_service import IngestionService
from app.services.mock_rag_engine import MockRAGEngine
from tests.unit.fakes_db import MemoryStore, make_fake_uow_factory
from tests.unit.fakes_redis import FakeRedis

PREFIX = "/api/v1/chatbot"
INTERNAL_KEY = "internal-secret"

_PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC_PEM = _PRIVATE.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
).decode()
_OTHER_PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_token(sub: str = "user-1", *, roles=None, expires_in: int = 3600, key=_PRIVATE) -> str:
    claims = {"sub": sub, "exp": int(time.time()) + expires_in}
    if roles is not None:
        claims["roles"] = roles
    return jwt.encode(claims, key, algorithm="RS256")


def forged_token(sub: str = "user-1") -> str:
    return make_token(sub, key=_OTHER_PRIVATE)


def auth(sub: str = "user-1", **kw) -> dict:
    return {"Authorization": f"Bearer {make_token(sub, **kw)}"}


class Ctx:
    def __init__(self, client, store, services, redis):
        self.client, self.store, self.services, self.redis = client, store, services, redis

    def url(self, path: str) -> str:
        return PREFIX + path


def build(monkeypatch, *, rag_engine=None, rate_limit: int = 100, allow_guest: bool = True,
          max_len: int = 1000, health=None, ingestion=None) -> Ctx:
    env = {
        "JWT_PUBLIC_KEY": PUBLIC_PEM, "JWT_ALGORITHM": "RS256", "ALLOW_GUEST": str(allow_guest).lower(),
        "INTERNAL_API_KEY": INTERNAL_KEY, "MESSAGE_MAX_LENGTH": str(max_len),
        "RATE_LIMIT_PER_MINUTE": str(rate_limit), "APP_ENV": "development", "TRUST_GATEWAY_USER_HEADER": "false",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    settings = get_settings()

    from app.main import create_app

    app = create_app()
    store = MemoryStore()
    uow = make_fake_uow_factory(store)
    redis = FakeRedis()
    conversations = ConversationService(uow)
    history = HistoryService(uow, None, max_turns=6, max_tokens=1500, count_tokens=len)
    rag = rag_engine or MockRAGEngine()
    services = Services(
        chat=ChatService(conversations=conversations, history=history, rag_engine=rag),
        conversations=conversations, history=history, feedback=FeedbackService(uow),
        health=health or HealthService(settings),
        ingestion=ingestion or IngestionService(uow, runner=_noop_runner),
        rate_limiter=RateLimiter(redis, settings.rate_limit_per_minute),
    )
    app.state.services = services
    return Ctx(TestClient(app), store, services, redis)


async def _noop_runner(mode):
    return {}
