"""Построители клавиатур VK (Keyboard API: текстовые кнопки с payload)."""
from __future__ import annotations

from vkbottle import Keyboard, KeyboardButtonColor, Text

from config.roles import ROLES
from keyboards.payloads import Cmd, payload
from models.chat import Dialog
from utils.text import BUTTON_LABEL_LIMIT, shorten

_PRIMARY = KeyboardButtonColor.PRIMARY
_POSITIVE = KeyboardButtonColor.POSITIVE
_NEGATIVE = KeyboardButtonColor.NEGATIVE
_SECONDARY = KeyboardButtonColor.SECONDARY


def _btn(label: str, cmd: Cmd, **args: object) -> Text:
    return Text(shorten(label, BUTTON_LABEL_LIMIT), payload(cmd, **args))


def main_menu() -> str:
    return (
        Keyboard(one_time=False, inline=False)
        .add(_btn("➕ Новый диалог", Cmd.NEW), _POSITIVE)
        .add(_btn("💬 Список диалогов", Cmd.LIST), _PRIMARY)
        .row()
        .add(_btn("🎭 Сменить режим", Cmd.ROLES), _PRIMARY)
        .add(_btn("⚙️ Настройки", Cmd.SETTINGS), _SECONDARY)
        .row()
        .add(_btn("❓ Помощь", Cmd.HELP), _SECONDARY)
        .get_json()
    )


def dialogs_list(dialogs: list[Dialog], active_id: str | None) -> str:
    """Строка на диалог: [переключить] [удалить]. Максимум 8 диалогов → 10 строк с нижними кнопками."""
    kb = Keyboard(one_time=False, inline=False)
    for number, dialog in enumerate(dialogs, start=1):
        is_active = dialog.id == active_id
        kb.add(
            _btn(f"{'✅' if is_active else '💬'} {number}. {dialog.title}", Cmd.SWITCH, id=dialog.id),
            _POSITIVE if is_active else _PRIMARY,
        )
        kb.add(_btn(f"🗑 Удалить {number}", Cmd.DELETE_ASK, id=dialog.id), _NEGATIVE)
        kb.row()
    kb.add(_btn("➕ Новый диалог", Cmd.NEW), _POSITIVE)
    kb.add(_btn("⬅️ В меню", Cmd.MENU), _SECONDARY)
    return kb.get_json()


def roles_menu(current_role_id: str) -> str:
    kb = Keyboard(one_time=False, inline=False)
    for role in ROLES:
        label = f"{'✅ ' if role.id == current_role_id else ''}{role.label}"
        kb.add(_btn(label, Cmd.SET_ROLE, id=role.id), _POSITIVE if role.id == current_role_id else _PRIMARY)
        kb.row()
    kb.add(_btn("⬅️ В меню", Cmd.MENU), _SECONDARY)
    return kb.get_json()


def settings_menu() -> str:
    return (
        Keyboard(one_time=False, inline=False)
        .add(_btn("🎭 Режим общения", Cmd.ROLES), _PRIMARY)
        .row()
        .add(_btn("✏️ Переименовать диалог", Cmd.RENAME), _PRIMARY)
        .row()
        .add(_btn("🧹 Очистить историю", Cmd.CLEAR_ASK), _NEGATIVE)
        .row()
        .add(_btn("⬅️ В меню", Cmd.MENU), _SECONDARY)
        .get_json()
    )


def confirm_clear() -> str:
    return (
        Keyboard(one_time=False, inline=False)
        .add(_btn("✅ Да, очистить", Cmd.CLEAR_YES), _NEGATIVE)
        .add(_btn("↩️ Отмена", Cmd.SETTINGS), _SECONDARY)
        .get_json()
    )


def cancel_only() -> str:
    return Keyboard(one_time=False, inline=False).add(_btn("↩️ Отмена", Cmd.CANCEL), _SECONDARY).get_json()


def confirm_delete(dialog_id: str) -> str:
    return (
        Keyboard(one_time=False, inline=False)
        .add(_btn("🗑 Да, удалить", Cmd.DELETE, id=dialog_id), _NEGATIVE)
        .add(_btn("↩️ Отмена", Cmd.LIST), _SECONDARY)
        .get_json()
    )
