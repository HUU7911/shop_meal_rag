import time

import jwt
import pytest

from app.core.config import get_settings
from app.core.errors import AuthenticationError, ConfigurationError
from app.core.security import CurrentUser, decode_jwt, is_valid_internal_key
from tests.unit.api_helpers import HS_SECRET, INTERNAL_KEY, PUBLIC_PEM, forged_token, make_token


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setenv("JWT_PUBLIC_KEY", PUBLIC_PEM)
    monkeypatch.setenv("JWT_ALGORITHM", "RS256")
    monkeypatch.setenv("JWT_SECRET", "")
    monkeypatch.setenv("JWT_ISSUER", "")
    monkeypatch.setenv("INTERNAL_API_KEY", INTERNAL_KEY)
    monkeypatch.delenv("JWT_AUDIENCE", raising=False)
    monkeypatch.delenv("JWT_JWKS_URL", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def hs_token(monkeypatch, **claims) -> str:
    base = {"sub": "u_1", "exp": int(time.time()) + 600, "roles": ["USER"], "typ": "access"}
    return jwt.encode({**base, **claims}, HS_SECRET, algorithm="HS256")


def use_hs256(monkeypatch, secret: str = HS_SECRET):
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("JWT_SECRET", secret)
    monkeypatch.setenv("JWT_PUBLIC_KEY", "")
    get_settings.cache_clear()


def test_valid_token_yields_subject_and_normalized_roles():
    claims = decode_jwt(make_token("u1", roles=["ROLE_ADMIN", "user"]))
    assert claims["sub"] == "u1" and claims["roles"] == ["ADMIN", "USER"]


def test_single_string_role_is_accepted():
    assert decode_jwt(make_token("u1", roles="admin"))["roles"] == ["ADMIN"]


def test_forged_expired_and_garbage_tokens_are_rejected():
    for bad in (forged_token(), make_token(expires_in=-5), "garbage"):
        with pytest.raises(AuthenticationError):
            decode_jwt(bad)


def test_hs256_works_only_with_a_configured_secret(monkeypatch):
    use_hs256(monkeypatch)
    assert decode_jwt(hs_token(monkeypatch))["sub"] == "u_1"
    with pytest.raises(AuthenticationError):
        decode_jwt(jwt.encode({"sub": "u_1", "exp": int(time.time()) + 600}, "k" * 48, algorithm="HS256"))   # sai khóa


def test_hs256_without_or_with_short_secret_is_a_configuration_error(monkeypatch):
    for secret in ("", "ngắn"):
        use_hs256(monkeypatch, secret)
        with pytest.raises(ConfigurationError):
            decode_jwt(hs_token(monkeypatch))


def test_algorithm_confusion_attack_is_rejected(monkeypatch):
    # Server cấu hình RS256; kẻ tấn công ký HS256 bằng chính khóa công khai làm "bí mật"
    forged = jwt.encode({"sub": "attacker", "exp": int(time.time()) + 600, "roles": ["ADMIN"]}, PUBLIC_PEM, algorithm="HS256")
    with pytest.raises(AuthenticationError):
        decode_jwt(forged)
    # Và ngược lại: server cấu hình HS256 thì token RS256 không được chấp nhận
    use_hs256(monkeypatch)
    with pytest.raises(AuthenticationError):
        decode_jwt(make_token("u1"))


def test_unknown_or_none_algorithm_is_refused(monkeypatch):
    for algorithm in ("none", "HS1", ""):
        monkeypatch.setenv("JWT_ALGORITHM", algorithm)
        get_settings.cache_clear()
        with pytest.raises(ConfigurationError):
            decode_jwt(make_token())


def test_missing_key_configuration_is_a_configuration_error(monkeypatch):
    monkeypatch.setenv("JWT_PUBLIC_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(ConfigurationError):
        decode_jwt(make_token())


def test_only_access_tokens_are_accepted(monkeypatch):
    use_hs256(monkeypatch)
    assert decode_jwt(hs_token(monkeypatch, typ="access"))
    with pytest.raises(AuthenticationError):
        decode_jwt(hs_token(monkeypatch, typ="refresh"))
    claims = {"sub": "u", "exp": int(time.time()) + 60}                    # token ngoài, không có typ
    assert decode_jwt(jwt.encode(claims, HS_SECRET, algorithm="HS256"))["sub"] == "u"


def test_issuer_is_enforced_when_configured(monkeypatch):
    use_hs256(monkeypatch)
    monkeypatch.setenv("JWT_ISSUER", "shop-meal-chatbot")
    get_settings.cache_clear()
    assert decode_jwt(hs_token(monkeypatch, iss="shop-meal-chatbot"))
    for bad in (hs_token(monkeypatch, iss="ke-tan-cong"), hs_token(monkeypatch)):       # sai iss, thiếu iss
        with pytest.raises(AuthenticationError):
            decode_jwt(bad)


def test_internal_key_comparison():
    assert is_valid_internal_key(INTERNAL_KEY)
    assert not is_valid_internal_key("wrong") and not is_valid_internal_key("") and not is_valid_internal_key(None)


def test_internal_key_unset_never_matches(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "")
    get_settings.cache_clear()
    assert not is_valid_internal_key("") and not is_valid_internal_key("anything")


def test_current_user_repr_does_not_leak_token():
    user = CurrentUser(user_id="u1", roles=("USER",), token="super-secret-jwt")
    assert "super-secret-jwt" not in repr(user) and not user.is_guest
    assert CurrentUser(user_id=None).is_guest