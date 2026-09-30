"""Обычные текстовые сообщения → ИИ. Регистрируется ПОСЛЕДНИМ (ловит всё, что не кнопка)."""
from __future__ import annotations

import logging
import time

from vkbottle.bot import BotLabeler, Message

from bot.container import Container
from keyboards import menus
from models.chat import PendingAction
from models.errors import BotError
from utils.text import shorten_head, split_message
from utils.typing_indicator import typing_indicator

logger = logging.getLogger(__name__)

THINKING_TEXT = "🤔 Бот думает..."
STREAM_PREVIEW_LIMIT = 4000


def _with_partial(partial: str, error_text: str) -> str:
    """Если ответ оборвался посреди потока — показываем то, что успело прийти, и причину."""
    return f"{partial}\n\n{error_text}" if partial else error_text


def register(labeler: BotLabeler, c: Container, edit_interval: float = 1.5) -> None:
    async def _edit(message: Message, cmid: int, text: str, keyboard: str | None = None) -> None:
        await message.ctx_api.messages.edit(
            peer_id=message.peer_id, conversation_message_id=cmid, message=text, keyboard=keyboard
        )

    async def _finish(message: Message, placeholder_cmid: int | None, text: str) -> None:
        """Заменяет «Бот думает…» ответом; длинный текст режется на части (лимит VK — 4096)."""
        first, *rest = split_message(text)
        edited = False
        if placeholder_cmid is not None:
            try:
                await _edit(message, placeholder_cmid, first, menus.main_menu())
                edited = True
            except Exception:
                logger.warning("Не удалось отредактировать сообщение-заглушку", exc_info=True)
        if not edited:
            await message.answer(first, keyboard=menus.main_menu())
        for part in rest:
            await message.answer(part)

    @labeler.private_message()
    async def on_text(message: Message) -> None:
        user_id = message.from_id
        try:
            data, _ = await c.dialogs.get_state(user_id)

            # Ждём от пользователя новое название диалога
            if data.settings.pending_action is PendingAction.RENAME_DIALOG:
                dialog = await c.dialogs.rename_active(user_id, message.text or "")
                await message.answer(f"✅ Диалог переименован: «{dialog.title}»", keyboard=menus.main_menu())
                return

            text = c.chat.precheck(user_id, message.text)  # валидация, «занят», лимит частоты
        except BotError as exc:
            await message.answer(exc.user_message, keyboard=menus.main_menu())
            return
        except Exception:
            logger.exception("Ошибка подготовки сообщения (user=%s)", user_id)
            await message.answer("⚠️ Произошла ошибка. Попробуйте ещё раз.", keyboard=menus.main_menu())
            return

        placeholder = await message.answer(THINKING_TEXT)
        cmid = getattr(placeholder, "conversation_message_id", None)
        buffer = ""
        try:
            async with typing_indicator(message.ctx_api, message.peer_id):
                last_edit = time.monotonic()
                async for delta in c.chat.stream_answer(user_id, text):
                    buffer += delta
                    now = time.monotonic()
                    if cmid is not None and now - last_edit >= edit_interval:
                        last_edit = now
                        try:  # промежуточная правка: сбой (лимиты VK и т. п.) не должен прерывать ответ
                            await _edit(message, cmid, shorten_head(buffer + " ▌", STREAM_PREVIEW_LIMIT))
                        except Exception:
                            logger.debug("Промежуточная правка не удалась", exc_info=True)
            reply = buffer
        except BotError as exc:
            reply = _with_partial(buffer, exc.user_message)
        except Exception:
            logger.exception("Сбой при генерации ответа (user=%s)", user_id)
            reply = _with_partial(buffer, "⚠️ Внутренняя ошибка. Попробуйте позже.")
        await _finish(message, cmid, reply)
