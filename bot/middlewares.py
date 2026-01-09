from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from sqlalchemy.ext.asyncio import AsyncSession

from database.engine import async_session_maker
from services.user_service import UserService


class DatabaseMiddleware(BaseMiddleware):
    """Middleware to provide database session to handlers."""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        async with async_session_maker() as session:
            try:
                data["session"] = session
                return await handler(event, data)
            except Exception:
                # Rollback on any error
                await session.rollback()
                raise


class UserMiddleware(BaseMiddleware):
    """Middleware to get or create user and add to handler data."""
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        session: AsyncSession = data.get("session")
        if session and event.from_user:
            user = await UserService.get_or_create_user(
                session,
                telegram_id=event.from_user.id,
                username=event.from_user.username,
                first_name=event.from_user.first_name,
                last_name=event.from_user.last_name,
            )
            data["user"] = user
        
        return await handler(event, data)

