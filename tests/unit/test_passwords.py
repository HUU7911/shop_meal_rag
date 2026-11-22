import unicodedata

from app.core.passwords import PasswordHasher, validate_password

FAST = PasswordHasher(n=2**4, r=1, p=1)         # tham số nhỏ để test nhanh; production dùng mặc định


def test_hash_verify_roundtrip_and_unique_salt():
    a, b = FAST.hash("Mat-khau-1"), FAST.hash("Mat-khau-1")
    assert a != b and a.startswith("scrypt$16$1$1$")
    assert FAST.verify("Mat-khau-1", a) and FAST.verify("Mat-khau-1", b)
    assert not FAST.verify("mat-khau-1", a) and not FAST.verify("", a)


def test_unicode_passwords_are_normalized():
    composed = "M\u1eadt kh\u1ea9u \u1ea1 1"                       # chữ có dấu dạng dựng sẵn
    decomposed = unicodedata.normalize("NFD", composed)           # cùng chữ nhưng dạng tách dấu
    assert composed != decomposed
    assert FAST.verify(decomposed, FAST.hash(composed))


def test_garbage_or_dangerous_stored_hashes_never_verify():
    for bad in ("", "plain", "scrypt$x$1$1$a$b", "md5$1$1$1$YQ==$YQ==", "scrypt$15$1$1$YQ==$YQ==",
                "scrypt$1048576$32$16$YQ==$YQ==", "scrypt$2097152$8$1$YQ==$YQ==", "scrypt$16$1$1$@@@$@@@"):
        assert FAST.verify("x", bad) is False


def test_needs_rehash_when_parameters_change():
    stored = FAST.hash("Mat-khau-1")
    assert not FAST.needs_rehash(stored)
    assert PasswordHasher(n=2**5, r=1, p=1).needs_rehash(stored)
    assert FAST.needs_rehash("không-phải-băm")


def test_default_parameters_are_the_documented_ones_and_work():
    default = PasswordHasher()
    stored = default.hash("Mat-khau-1")
    assert stored.startswith("scrypt$32768$8$3$") and default.verify("Mat-khau-1", stored)


async def test_async_helpers_and_timing_burn():
    stored = await FAST.ahash("Mat-khau-1")
    assert await FAST.averify("Mat-khau-1", stored) and not await FAST.averify("sai", stored)
    await FAST.burn("bất kỳ")        # không ném lỗi, không trả giá trị


def test_password_policy():
    assert validate_password("Mat-khau-1") is None
    assert "ít nhất 8" in validate_password("Ab1")
    assert "tối đa 128" in validate_password("a" * 129 + "B1")
    assert validate_password("password") and validate_password("12345678") and validate_password("aaaaaaaaaa")
    assert validate_password("        ")
    assert "email" in validate_password("nguyenvan-2024", email="nguyenvan@gmail.com")
    assert validate_password("Mat-khau-1", email="ab@x.com") is None          # tên email quá ngắn: bỏ qua
    assert validate_password("Abcdefg1", min_length=12)