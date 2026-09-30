"""Доменные модели. Не зависят ни от VK, ни от LLM."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field

from config.roles import DEFAULT_ROLE_ID


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(BaseModel):
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=utcnow)


class Dialog(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    title: str
    role_id: str = DEFAULT_ROLE_ID
    title_is_auto: bool = True  # название ещё не задано пользователем вручную
    summary: str = ""  # краткое содержание сообщений, вышедших за окно памяти
    messages: list[ChatMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class PendingAction(StrEnum):
    RENAME_DIALOG = "rename_dialog"


class UserSettings(BaseModel):
    pending_action: PendingAction | None = None  # ожидаем ли особый ввод (напр. новое имя)


class UserData(BaseModel):
    user_id: int
    dialogs: list[Dialog] = Field(default_factory=list)
    active_dialog_id: str | None = None
    settings: UserSettings = Field(default_factory=UserSettings)

    def get_dialog(self, dialog_id: str | None) -> Dialog | None:
        return next((d for d in self.dialogs if d.id == dialog_id), None)
