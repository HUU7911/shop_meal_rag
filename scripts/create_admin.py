"""Tạo (hoặc nâng quyền) tài khoản quản trị. Mật khẩu nhập tại dòng lệnh, không lưu trong .env hay lịch sử shell.

    python -m scripts.create_admin admin@shopmeal.vn
    python -m scripts.create_admin admin@shopmeal.vn --name "Quản trị viên"
    python -m scripts.create_admin nguoidung@shopmeal.vn --promote     # chỉ cấp ADMIN cho tài khoản đã có
"""
import argparse
import asyncio
import getpass
import sys

from app.core.config import get_settings
from app.core.ids import new_id
from app.core.passwords import PasswordHasher, validate_password
from app.db.models.auth import User
from app.db.session import create_engine_and_sessionmaker
from app.db.types import utcnow
from app.db.unit_of_work import make_uow_factory
from app.schemas.auth_schema import normalize_email


async def run(email: str, name: str | None, promote_only: bool) -> int:
    get_settings()
    email = normalize_email(email)
    engine, session_factory = create_engine_and_sessionmaker()
    try:
        async with make_uow_factory(session_factory)() as uow:
            user = await uow.users.get_by_email(email)
            if user is not None:
                user.roles = sorted(set(user.roles or []) | {"USER", "ADMIN"})
                user.is_active = True
                print(f"Đã cấp quyền ADMIN cho {email}.")
                return 0
            if promote_only:
                print(f"Không có tài khoản {email} để nâng quyền.", file=sys.stderr)
                return 1

            password = getpass.getpass("Mật khẩu: ")
            if password != getpass.getpass("Nhập lại mật khẩu: "):
                print("Hai lần nhập không khớp.", file=sys.stderr)
                return 1
            problem = validate_password(password, email=email, min_length=10)
            if problem:
                print(problem, file=sys.stderr)
                return 1

            now = utcnow()
            await uow.users.add(User(
                id=new_id("u"), email=email, password_hash=await PasswordHasher().ahash(password),
                full_name=name, roles=["USER", "ADMIN"], is_active=True, failed_login_count=0,
                password_changed_at=now, created_at=now, updated_at=now,
            ))
            print(f"Đã tạo quản trị viên {email}.")
            return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("email")
    parser.add_argument("--name")
    parser.add_argument("--promote", action="store_true", help="chỉ nâng quyền tài khoản đã tồn tại")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.email, args.name, args.promote)))