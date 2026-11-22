"""Repository: chỉ truy cập DB (không chứa nghiệp vụ)."""
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.db.models.auth import User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: str) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        return (await self.session.execute(select(User).where(User.email == email))).scalar_one_or_none()

    async def add(self, user: User) -> User:
        self.session.add(user)
        try:
            await self.session.flush()
        except IntegrityError as exc:          # hai request đăng ký cùng email cùng lúc: ràng buộc duy nhất chặn lại
            raise ConflictError("Email này đã được đăng ký.") from exc
        return user

    async def list_page(self, offset: int, limit: int) -> tuple[list[User], int]:
        total = await self.session.scalar(select(func.count()).select_from(User))
        rows = (
            await self.session.execute(select(User).order_by(User.created_at.desc(), User.id).offset(offset).limit(limit))
        ).scalars().all()
        return list(rows), total or 0

    async def count_active_admins(self) -> int:
        roles_of_active = (await self.session.execute(select(User.roles).where(User.is_active.is_(True)))).scalars().all()
        return sum(1 for roles in roles_of_active if "ADMIN" in (roles or []))