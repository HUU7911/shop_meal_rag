import pytest

from app.core.config import get_settings
from app.core.errors import AuthenticationError, ConfigurationError
from app.core.security import CurrentUser, decode_jwt, is_valid_internal_key
from tests.unit.api_helpers import INTERNAL_KEY, PUBLIC_PEM, forged_token, make_token


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setenv("JWT_PUBLIC_KEY", PUBLIC_PEM)
    monkeypatch.setenv("JWT_ALGORITHM", "RS256")
    monkeypatch.setenv("INTERNAL_API_KEY", INTERNAL_KEY)
    monkeypatch.delenv("JWT_AUDIENCE", raising=False)
    monkeypatch.delenv("JWT_JWKS_URL", raising=False)
    get_settings.cache_clear()
    yield
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


def test_symmetric_algorithms_are_refused(monkeypatch):
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")          # chống tấn công "alg confusion"
    get_settings.cache_clear()
    with pytest.raises(ConfigurationError):
        decode_jwt(make_token())


def test_missing_key_configuration_is_a_configuration_error(monkeypatch):
    monkeypatch.setenv("JWT_PUBLIC_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(ConfigurationError):
        decode_jwt(make_token())


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
