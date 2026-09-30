"""Контейнер зависимостей: собирается один раз в app.py и передаётся в обработчики."""
from __future__ import annotations

from dataclasses import dataclass

from services.chat_service import ChatService
from services.dialog_manager import DialogManager
from services.memory_manager import MemoryManager


@dataclass(frozen=True, slots=True)
class Container:
    dialogs: DialogManager
    memory: MemoryManager
    chat: ChatService
    max_dialogs: int
