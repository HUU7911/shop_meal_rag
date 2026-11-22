from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core import tokens
from app.core.errors import ConfigurationError


class Secret:
    def __init__(self, value: str):
        self.value = value

    def get_secret_value(self) -> str:
        return self.value


class Cfg:
    def __init__(self, **kw):
        self.jwt_algorithm = "HS256"
        self.jwt_secret = Secret("s" * 40)
        self.jwt_private_key = Secret("")
        self.jwt_public_key = ""
        self.jwt_jwks_url = ""
        self.jwt_issuer = "shop-meal-chatbot"
        self.jwt_audience = ""
        self.jwt_access_ttl_minutes = 30
        for k, v in kw.items():
            setattr(self, k, v)


_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIVATE_PEM = _KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption()).decode()


def test_hs256_token_has_the_expected_claims_and_verifies_with_the_secret():
    cfg = Cfg()
    token, ttl = tokens.create_access_token(cfg, user_id="u_1", roles=["USER", "ADMIN"], email="a@b.vn")
    claims = jwt.decode(token, tokens.static_verification_key(cfg), algorithms=["HS256"], issuer="shop-meal-chatbot")
    assert ttl == 1800 and claims["sub"] == "u_1" and claims["roles"] == ["USER", "ADMIN"]
    assert claims["typ"] == "access" and claims["email"] == "a@b.vn" and claims["exp"] - claims["iat"] == 1800
    assert len(claims["jti"]) == 32


def test_each_token_gets_a_unique_jti():
    cfg = Cfg()
    a = jwt.decode(tokens.create_access_token(cfg, user_id="u", roles=[])[0], options={"verify_signature": False})
    b = jwt.decode(tokens.create_access_token(cfg, user_id="u", roles=[])[0], options={"verify_signature": False})
    assert a["jti"] != b["jti"]


def test_issuer_and_audience_are_optional():
    token, _ = tokens.create_access_token(Cfg(jwt_issuer="", jwt_audience="shop"), user_id="u", roles=[])
    claims = jwt.decode(token, options={"verify_signature": False})
    assert "iss" not in claims and claims["aud"] == "shop"


def test_expiry_follows_the_clock():
    past = datetime.now(UTC) - timedelta(hours=2)
    token, _ = tokens.create_access_token(Cfg(), user_id="u", roles=[], now=past)
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(token, "s" * 40, algorithms=["HS256"])


def test_rs256_signs_with_private_key_and_verifies_with_derived_public_key():
    cfg = Cfg(jwt_algorithm="RS256", jwt_private_key=Secret(PRIVATE_PEM.replace("\n", "\\n")))   # PEM một dòng trong .env
    token, _ = tokens.create_access_token(cfg, user_id="u_2", roles=["USER"])
    public = tokens.static_verification_key(cfg)
    assert "BEGIN PUBLIC KEY" in public
    assert jwt.decode(token, public, algorithms=["RS256"], issuer="shop-meal-chatbot")["sub"] == "u_2"


def test_explicit_public_key_wins_over_the_derived_one():
    cfg = Cfg(jwt_algorithm="RS256", jwt_public_key="-----BEGIN PUBLIC KEY-----\\nabc\\n-----END PUBLIC KEY-----",
              jwt_private_key=Secret(PRIVATE_PEM))
    assert tokens.static_verification_key(cfg).count("\n") == 2


def test_configuration_checks():
    assert tokens.has_verification_key(Cfg()) and tokens.can_issue(Cfg())
    assert not tokens.has_verification_key(Cfg(jwt_secret=Secret("ngắn")))
    assert not tokens.can_issue(Cfg(jwt_secret=Secret("")))
    rs = Cfg(jwt_algorithm="RS256")
    assert not tokens.has_verification_key(rs) and not tokens.can_issue(rs)
    assert tokens.has_verification_key(Cfg(jwt_algorithm="RS256", jwt_public_key="pem")) and not tokens.can_issue(Cfg(jwt_algorithm="RS256", jwt_public_key="pem"))
    with pytest.raises(ConfigurationError):
        tokens.signing_key(Cfg(jwt_secret=Secret("ngắn")))
    with pytest.raises(ConfigurationError):
        tokens.signing_key(rs)
    with pytest.raises(ConfigurationError):
        tokens.algorithm_of(Cfg(jwt_algorithm="none"))


def test_refresh_tokens_are_random_and_only_their_hash_is_comparable():
    a, b = tokens.new_refresh_token(), tokens.new_refresh_token()
    assert a != b and len(a) >= 60
    assert tokens.hash_refresh_token(a) == tokens.hash_refresh_token(a) != tokens.hash_refresh_token(b)
    assert len(tokens.hash_refresh_token(a)) == 64 and a not in tokens.hash_refresh_token(a)