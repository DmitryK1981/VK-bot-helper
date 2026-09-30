from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager

from models.chat import UserData


class UserRepository(ABC):
    """Контракт хранилища. Чтобы сменить JSON на Redis/БД — реализуйте этот интерфейс."""

    @abstractmethod
    def transaction(self, user_id: int) -> AbstractAsyncContextManager[UserData]:
        """Эксклюзивный доступ к данным пользователя: изменения сохраняются при выходе без ошибки."""

    @abstractmethod
    async def read(self, user_id: int) -> UserData:
        """Чтение (без гарантии эксклюзивности); файл создаётся, если его нет."""
