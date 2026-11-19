"""Sinh id có tiền tố, ví dụ c_<32 hex> (conversation), m_<...> (message), f_<...> (feedback).
Độ dài tối đa 34 ký tự, nằm trong cột String(40)."""
from uuid import uuid4


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
