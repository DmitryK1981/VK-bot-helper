from __future__ import annotations

from vkbottle.bot import BotLabeler, Message

from bot.container import Container
from bot.handlers.common import guarded
from bot.presenters import HELP_TEXT, dialog_card
from bot.rules import CmdRule, TextCommandRule
from keyboards import menus
from keyboards.payloads import Cmd

WELCOME = (
    "👋 Привет! Я умный AI-помощник.\n\n"
    "Задавайте любые вопросы обычным сообщением — я отвечу и запомню контекст беседы. "
    "Управлять диалогами и режимами общения можно кнопками внизу."
)


def register(labeler: BotLabeler, c: Container) -> None:
    @labeler.private_message(TextCommandRule("начать", "старт", "меню", "/start", "/menu"))
    @labeler.private_message(CmdRule(Cmd.MENU))
    @guarded
    async def show_menu(message: Message) -> None:
        _, dialog = await c.dialogs.get_state(message.from_id)
        await c.dialogs.cancel_pending(message.from_id)
        await message.answer(f"{WELCOME}\n\n{dialog_card(dialog)}", keyboard=menus.main_menu())

    @labeler.private_message(CmdRule(Cmd.HELP))
    @guarded
    async def show_help(message: Message) -> None:
        await message.answer(HELP_TEXT, keyboard=menus.main_menu())
