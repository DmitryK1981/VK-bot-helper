from __future__ import annotations

from vkbottle.bot import Message
from vkbottle.dispatch.rules import ABCRule

from keyboards.payloads import Cmd


class CmdRule(ABCRule[Message]):
    """Срабатывает на нажатие кнопки с payload {"cmd": <cmd>}."""

    def __init__(self, cmd: Cmd) -> None:
        self.cmd = cmd.value

    async def check(self, event: Message) -> bool:
        data = event.get_payload_json()
        return isinstance(data, dict) and data.get("cmd") == self.cmd


class TextCommandRule(ABCRule[Message]):
    """Текстовые команды без учёта регистра: «Меню», «/start» и т. п."""

    def __init__(self, *commands: str) -> None:
        self.commands = {c.lower() for c in commands}

    async def check(self, event: Message) -> bool:
        return (event.text or "").strip().lower() in self.commands


def payload_arg(message: Message, key: str) -> str:
    data = message.get_payload_json()
    return str(data.get(key, "")) if isinstance(data, dict) else ""
