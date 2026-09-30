"""Команды кнопок. Каждая кнопка несёт payload {"cmd": <команда>, ...аргументы}."""
from __future__ import annotations

from enum import StrEnum
from typing import Any


class Cmd(StrEnum):
    MENU = "menu"
    NEW = "new"
    LIST = "list"
    SWITCH = "switch"      # + id
    DELETE_ASK = "delete_ask"  # + id
    DELETE = "delete"      # + id (после подтверждения)
    ROLES = "roles"
    SET_ROLE = "set_role"  # + id
    SETTINGS = "settings"
    RENAME = "rename"
    CANCEL = "cancel"
    CLEAR_ASK = "clear_ask"
    CLEAR_YES = "clear_yes"
    HELP = "help"


def payload(cmd: Cmd, **args: Any) -> dict[str, Any]:
    return {"cmd": cmd.value, **args}
