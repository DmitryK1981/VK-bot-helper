"""Менеджер памяти: краткосрочная история диалога (окно из N сообщений) + краткое содержание."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from models.chat import ChatMessage, Dialog, MessageRole
from storage.base import UserRepository

logger = logging.getLogger(__name__)

_AUTO_TITLE_LENGTH = 30
_HARD_CAP_EXTRA = 40  # аварийный предел: если суммаризация не работает, история всё равно не растёт бесконечно


@dataclass(frozen=True, slots=True)
class CompactionJob:
    """Что нужно свернуть в резюме: `count` самых старых сообщений диалога."""

    dialog_id: str
    previous_summary: str
    messages: list[ChatMessage]

    @property
    def count(self) -> int:
        return len(self.messages)


class MemoryManager:
    def __init__(self, repo: UserRepository, max_messages: int, summary_batch: int = 20) -> None:
        self._repo = repo
        self._max = max_messages
        self._batch = summary_batch

    @property
    def max_messages(self) -> int:
        return self._max

    async def append_exchange(
        self, user_id: int, dialog_id: str, user_text: str, assistant_text: str
    ) -> None:
        """Сохраняет пару «вопрос-ответ». Лишнее сворачивается отдельно (plan/commit_compaction)."""
        async with self._repo.transaction(user_id) as data:
            dialog = data.get_dialog(dialog_id)
            if dialog is None:  # диалог удалили, пока шёл запрос к модели
                return
            self._auto_title(dialog, user_text)
            dialog.messages.append(ChatMessage(role=MessageRole.USER, content=user_text))
            dialog.messages.append(ChatMessage(role=MessageRole.ASSISTANT, content=assistant_text))
            del dialog.messages[: -(self._max + _HARD_CAP_EXTRA)]

    # ---------- суммаризация ----------
    async def plan_compaction(self, user_id: int, dialog_id: str) -> CompactionJob | None:
        """Если сообщений больше окна — выбирает самые старые для сворачивания (с запасом на batch)."""
        async with self._repo.transaction(user_id) as data:
            dialog = data.get_dialog(dialog_id)
            if dialog is None or len(dialog.messages) <= self._max:
                return None
            count = len(dialog.messages) - self._max + self._batch
            count = min(count, len(dialog.messages) - 1)
            return CompactionJob(
                dialog_id, dialog.summary, [m.model_copy() for m in dialog.messages[:count]]
            )

    async def commit_compaction(self, user_id: int, job: CompactionJob, new_summary: str | None) -> bool:
        """Удаляет свёрнутые сообщения; new_summary=None — ИИ недоступен, просто отбрасываем старое."""
        async with self._repo.transaction(user_id) as data:
            dialog = data.get_dialog(job.dialog_id)
            if dialog is None:
                return False
            head = dialog.messages[: job.count]
            if [m.timestamp for m in head] != [m.timestamp for m in job.messages]:
                return False  # историю успели изменить (очистка и т. п.) — план устарел
            del dialog.messages[: job.count]
            if new_summary:
                dialog.summary = new_summary
            return True

    # ---------- прочее ----------
    async def clear(self, user_id: int) -> None:
        """Очистка истории: удаляются и сообщения, и краткое содержание."""
        async with self._repo.transaction(user_id) as data:
            dialog = data.get_dialog(data.active_dialog_id)
            if dialog is not None:
                dialog.messages.clear()
                dialog.summary = ""

    @staticmethod
    def _auto_title(dialog: Dialog, first_text: str) -> None:
        if dialog.title_is_auto and not dialog.messages:
            title = " ".join(first_text.split())[:_AUTO_TITLE_LENGTH].strip()
            if title:
                dialog.title = title
