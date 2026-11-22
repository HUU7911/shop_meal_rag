"""Băm và kiểm tra mật khẩu bằng scrypt của thư viện chuẩn (không cần cài thêm gói).

* Định dạng lưu: scrypt$N$r$p$salt$hash (base64). Tham số nằm trong chuỗi băm nên đổi tham số sau này không làm
  hỏng mật khẩu cũ; `needs_rehash` cho biết khi nào nên băm lại lúc người dùng đăng nhập.
* Mặc định N=2^15, r=8, p=3 (32 MiB): cấu hình scrypt tương đương mức tối thiểu OWASP khuyến nghị.
* Băm chạy trong thread (không chặn event loop) và giới hạn số lượt chạy đồng thời để request đăng nhập dồn dập
  không làm cạn bộ nhớ.
"""
import asyncio
import base64
import hashlib
import hmac
import secrets
import threading
import unicodedata

MAX_PASSWORD_LENGTH = 128
_SALT_BYTES = 16
_DKLEN = 32
_COMMON = {
    "password", "password1", "password123", "12345678", "123456789", "1234567890", "qwertyui", "qwerty123",
    "11111111", "00000000", "iloveyou", "abc12345", "matkhau123", "admin123", "letmein1",
}


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _prepare(password: str) -> bytes:
    # NFKC để cùng một mật khẩu gõ trên các bộ gõ khác nhau cho cùng kết quả
    return unicodedata.normalize("NFKC", password).encode("utf-8")


class PasswordHasher:
    def __init__(self, n: int = 2**15, r: int = 8, p: int = 3, *, max_concurrent: int = 4):
        self.n, self.r, self.p = n, r, p
        self._limit = threading.BoundedSemaphore(max_concurrent)
        self._dummy: str | None = None
        self._dummy_lock = threading.Lock()

    # ---------- đồng bộ ----------
    def _derive(self, password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
        maxmem = 128 * r * (n + p + 2) + 2**20
        return hashlib.scrypt(_prepare(password), salt=salt, n=n, r=r, p=p, maxmem=maxmem, dklen=_DKLEN)

    def hash(self, password: str) -> str:
        salt = secrets.token_bytes(_SALT_BYTES)
        digest = self._derive(password, salt, self.n, self.r, self.p)
        return f"scrypt${self.n}${self.r}${self.p}${_b64(salt)}${_b64(digest)}"

    @staticmethod
    def _parse(stored: str) -> tuple[int, int, int, bytes, bytes] | None:
        try:
            scheme, n, r, p, salt, digest = stored.split("$")
            if scheme != "scrypt":
                return None
            n_i, r_i, p_i = int(n), int(r), int(p)
            # chặn tham số bất thường (dữ liệu hỏng/độc hại) để không bị dùng làm đòn tấn công cạn tài nguyên
            if n_i < 2 or n_i & (n_i - 1) or n_i > 2**20 or not 1 <= r_i <= 32 or not 1 <= p_i <= 16:
                return None
            return n_i, r_i, p_i, base64.b64decode(salt), base64.b64decode(digest)
        except (ValueError, TypeError):
            return None

    def verify(self, password: str, stored: str) -> bool:
        parsed = self._parse(stored)
        if parsed is None:
            return False
        n, r, p, salt, expected = parsed
        try:
            actual = self._derive(password, salt, n, r, p)
        except (ValueError, MemoryError):
            return False
        return hmac.compare_digest(actual, expected)

    def needs_rehash(self, stored: str) -> bool:
        parsed = self._parse(stored)
        return parsed is None or parsed[:3] != (self.n, self.r, self.p)

    # ---------- bất đồng bộ (dùng trong service) ----------
    def _guarded(self, fn, *args):
        with self._limit:
            return fn(*args)

    async def ahash(self, password: str) -> str:
        return await asyncio.to_thread(self._guarded, self.hash, password)

    async def averify(self, password: str, stored: str) -> bool:
        return await asyncio.to_thread(self._guarded, self.verify, password, stored)

    async def burn(self, password: str) -> None:
        """Tốn đúng một lần băm khi email không tồn tại, để thời gian phản hồi không lộ email nào có trong hệ thống."""
        with self._dummy_lock:
            if self._dummy is None:
                self._dummy = self.hash("mat-khau-gia-de-dong-bo-thoi-gian")
        await self.averify(password, self._dummy)


def validate_password(password: str, *, email: str | None = None, min_length: int = 8) -> str | None:
    """Trả thông báo lỗi (tiếng Việt) nếu mật khẩu không đạt yêu cầu, ngược lại None."""
    if len(password) < min_length:
        return f"Mật khẩu cần ít nhất {min_length} ký tự."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Mật khẩu tối đa {MAX_PASSWORD_LENGTH} ký tự."
    if not password.strip():
        return "Mật khẩu không được chỉ gồm khoảng trắng."
    if password.lower() in _COMMON or len(set(password)) < 4:
        return "Mật khẩu quá dễ đoán, hãy chọn mật khẩu khác."
    if email:
        local = email.split("@", 1)[0].lower()
        if len(local) >= 4 and local in password.lower():
            return "Mật khẩu không được chứa phần tên của email."
    return None