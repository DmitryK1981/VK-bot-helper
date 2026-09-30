from __future__ import annotations

import functools
import logging
from typing import Awaitable, Callable

from vkbottle.bot import Message

from keyboards import menus
from models.errors import BotError

logger = logging.getLogger(__name__)

Handler = Callable[[Message], Awaitable[None]]


def guarded(handler: Handler) -> Handler:
    """Превращает любые ошибки обработчика в понятное пользователю сообщение."""

    @functools.wraps(handler)
    async def wrapper(message: Message) -> None:
        try:
            await handler(message)
        except BotError as exc:
            await message.answer(exc.user_message, keyboard=menus.main_menu())
        except Exception:
            logger.exception("Необработанная ошибка в %s (user=%s)", handler.__name__, message.from_id)
            await message.answer(
                "⚠️ Что-то пошло не так. Попробуйте ещё раз или нажмите «⬅️ В меню».",
                keyboard=menus.main_menu(),
            )

    return wrapper
