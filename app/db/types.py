"""Kiểu cột dùng chung. Mọi thời điểm trong bảng chat được lưu UTC, KHÔNG múi giờ, độ chính xác micro-giây.

Vì sao DATETIME(6): MySQL mặc định DATETIME chỉ tới giây; hai message (user + assistant) lưu cùng giây
sẽ có created_at trùng nhau -> thứ tự lịch sử hội thoại không xác định.
"""
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.dialects import mysql

UTCDateTime = DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
