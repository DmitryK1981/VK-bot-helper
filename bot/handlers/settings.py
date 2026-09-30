from __future__ import annotations

from vkbottle.bot import BotLabeler, Message

from bot.container import Container
from bot.handlers.common import guarded
from bot.presenters import dialog_card
from bot.rules import CmdRule, payload_arg
from config.roles import ROLES, get_role
from keyboards import menus
from keyboards.payloads import Cmd


def register(labeler: BotLabeler, c: Container) -> None:
    async def _settings_screen(message: Message, prefix: str = "") -> None:
        _, dialog = await c.dialogs.get_state(message.from_id)
        await message.answer(
            f"{prefix}⚙️ Настройки\n\n{dialog_card(dialog)}\n🤖 Модель: {c.chat.model_name}",
            keyboard=menus.settings_menu(),
        )

    @labeler.private_message(CmdRule(Cmd.SETTINGS))
    @guarded
    async def settings(message: Message) -> None:
        await c.dialogs.cancel_pending(message.from_id)
        await _settings_screen(message)

    # ---------- режимы общения ----------
    @labeler.private_message(CmdRule(Cmd.ROLES))
    @guarded
    async def roles(message: Message) -> None:
        _, dialog = await c.dialogs.get_state(message.from_id)
        catalog = "\n".join(f"{r.label} — {r.description}" for r in ROLES)
        await message.answer(
            f"🎭 Выберите режим общения для диалога «{dialog.title}»:\n\n{catalog}\n\n"
            "Остальные диалоги не изменятся.",
            keyboard=menus.roles_menu(dialog.role_id),
        )

    @labeler.private_message(CmdRule(Cmd.SET_ROLE))
    @guarded
    async def set_role(message: Message) -> None:
        dialog, role = await c.dialogs.set_role(message.from_id, payload_arg(message, "id"))
        await message.answer(
            f"✅ Режим изменён: {role.label}\n{role.description}\n\n"
            f"Новый стиль применён к диалогу «{dialog.title}». История сохранена.",
            keyboard=menus.main_menu(),
        )

    # ---------- переименование ----------
    @labeler.private_message(CmdRule(Cmd.RENAME))
    @guarded
    async def rename(message: Message) -> None:
        dialog = await c.dialogs.begin_rename(message.from_id)
        await message.answer(
            f"✏️ Текущее название: «{dialog.title}».\nНапишите новое название (до 30 символов):",
            keyboard=menus.cancel_only(),
        )

    @labeler.private_message(CmdRule(Cmd.CANCEL))
    @guarded
    async def cancel(message: Message) -> None:
        await c.dialogs.cancel_pending(message.from_id)
        await message.answer("Отменено.", keyboard=menus.main_menu())

    # ---------- очистка истории ----------
    @labeler.private_message(CmdRule(Cmd.CLEAR_ASK))
    @guarded
    async def clear_ask(message: Message) -> None:
        _, dialog = await c.dialogs.get_state(message.from_id)
        await message.answer(
            f"🧹 Очистить историю диалога «{dialog.title}» ({len(dialog.messages)} сообщ.)?\n"
            "Бот забудет этот разговор. Отменить это действие нельзя.",
            keyboard=menus.confirm_clear(),
        )

    @labeler.private_message(CmdRule(Cmd.CLEAR_YES))
    @guarded
    async def clear_yes(message: Message) -> None:
        await c.memory.clear(message.from_id)
        await message.answer("✅ История очищена. Режим общения сохранён.", keyboard=menus.main_menu())
