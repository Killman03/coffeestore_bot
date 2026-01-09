from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from database.models import User
from config import settings


class UserService:
    """Service for user management."""
    
    @staticmethod
    async def get_or_create_user(
        session: AsyncSession,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> User:
        """Get existing user or create new one."""
        # Try to get existing user
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if user:
            # Update user information
            user.username = username
            user.first_name = first_name
            user.last_name = last_name
            if first_name and last_name:
                user.full_name = f"{first_name} {last_name}"
            elif first_name:
                user.full_name = first_name
            elif username:
                user.full_name = username
            else:
                user.full_name = f"User {telegram_id}"
            await session.commit()
            return user
        
        # Create new user
        full_name = ""
        if first_name and last_name:
            full_name = f"{first_name} {last_name}"
        elif first_name:
            full_name = first_name
        elif username:
            full_name = username
        else:
            full_name = f"User {telegram_id}"
        
        is_admin = telegram_id in settings.admin_list
        
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            full_name=full_name,
            is_admin=is_admin,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user
    
    @staticmethod
    async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[User]:
        """Get user by telegram ID."""
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_all_active_sellers(session: AsyncSession) -> list[User]:
        """Get all active sellers."""
        result = await session.execute(
            select(User).where(User.is_active == True).order_by(User.full_name)
        )
        return list(result.scalars().all())

    @staticmethod
    async def add_seller(session: AsyncSession, telegram_id: int, full_name: str, username: Optional[str] = None) -> User:
        """Create or activate seller by telegram id."""
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user:
            user.full_name = full_name or user.full_name
            user.username = username or user.username
            user.is_active = True
        else:
            user = User(
                telegram_id=telegram_id,
                full_name=full_name or f"User {telegram_id}",
                username=username,
                is_active=True,
            )
            session.add(user)
        await session.commit()
        await session.refresh(user)
        return user
    
    @staticmethod
    async def is_admin(session: AsyncSession, telegram_id: int) -> bool:
        """Check if user is admin."""
        user = await UserService.get_user_by_telegram_id(session, telegram_id)
        return user.is_admin if user else False

