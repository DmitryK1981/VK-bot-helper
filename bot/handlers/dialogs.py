from __future__ import annotations

from vkbottle.bot import BotLabeler, Message

from bot.container import Container
from bot.handlers.common import guarded
from bot.presenters import dialog_card, dialogs_overview
from bot.rules import CmdRule, payload_arg
from keyboards import menus
from keyboards.payloads import Cmd


def register(labeler: BotLabeler, c: Container) -> None:
    async def _show_list(message: Message, prefix: str = "") -> None:
        data, _ = await c.dialogs.get_state(message.from_id)
        text = dialogs_overview(data.dialogs, data.active_dialog_id, c.max_dialogs)
        await message.answer(prefix + text, keyboard=menus.dialogs_list(data.dialogs, data.active_dialog_id))

    @labeler.private_message(CmdRule(Cmd.NEW))
    @guarded
    async def new_dialog(message: Message) -> None:
        dialog = await c.dialogs.create_dialog(message.from_id)
        await message.answer(
            f"✨ Новый диалог создан и выбран.\n\n{dialog_card(dialog)}\n\n"
            "Напишите первое сообщение — контекст предыдущих диалогов учитываться не будет.",
            keyboard=menus.main_menu(),
        )

    @labeler.private_message(CmdRule(Cmd.LIST))
    @guarded
    async def list_dialogs(message: Message) -> None:
        await _show_list(message)

    @labeler.private_message(CmdRule(Cmd.SWITCH))
    @guarded
    async def switch_dialog(message: Message) -> None:
        dialog = await c.dialogs.switch(message.from_id, payload_arg(message, "id"))
        await message.answer(
            f"🔀 Переключено на другой диалог.\n\n{dialog_card(dialog)}\n\n"
            "Продолжайте общение — я помню этот разговор.",
            keyboard=menus.main_menu(),
        )

    @labeler.private_message(CmdRule(Cmd.DELETE_ASK))
    @guarded
    async def delete_ask(message: Message) -> None:
        data, _ = await c.dialogs.get_state(message.from_id)
        dialog = data.get_dialog(payload_arg(message, "id"))
        if dialog is None:
            await _show_list(message, prefix="Такого диалога уже нет 🤷\n\n")
            return
        await message.answer(
            f"🗑 Удалить диалог «{dialog.title}» ({len(dialog.messages)} сообщ.)?\n"
            "История будет удалена безвозвратно.",
            keyboard=menus.confirm_delete(dialog.id),
        )

    @labeler.private_message(CmdRule(Cmd.DELETE))
    @guarded
    async def delete_dialog(message: Message) -> None:
        active = await c.dialogs.delete(message.from_id, payload_arg(message, "id"))
        await _show_list(message, prefix=f"🗑 Диалог удалён. Сейчас активен: «{active.title}».\n\n")
