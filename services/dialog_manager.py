"""Менеджер диалогов: создание, переключение, переименование, удаление, смена роли."""
from __future__ import annotations

from config.roles import ROLES_BY_ID, Role, get_role
from models.chat import Dialog, PendingAction, UserData
from models.errors import BotError, DialogLimitError, DialogNotFoundError
from storage.base import UserRepository

MAX_TITLE_LENGTH = 30


def normalize_title(raw: str) -> str:
    return " ".join(raw.split())[:MAX_TITLE_LENGTH].strip()


class DialogManager:
    def __init__(self, repo: UserRepository, max_dialogs: int) -> None:
        self._repo = repo
        self._max_dialogs = max_dialogs

    # ---------- внутреннее ----------
    @staticmethod
    def _new_dialog(data: UserData) -> Dialog:
        titles = {d.title for d in data.dialogs}
        number = 1
        while f"Диалог {number}" in titles:
            number += 1
        dialog = Dialog(title=f"Диалог {number}")
        data.dialogs.append(dialog)
        data.active_dialog_id = dialog.id
        return dialog

    @staticmethod
    def _require(data: UserData, dialog_id: str | None) -> Dialog:
        dialog = data.get_dialog(dialog_id)
        if dialog is None:
            raise DialogNotFoundError("Такого диалога уже нет 🤷 Откройте список диалогов заново.")
        return dialog

    def _ensure_active(self, data: UserData) -> Dialog:
        """Активный диалог; если его нет (новый пользователь) — берём последний или создаём первый."""
        dialog = data.get_dialog(data.active_dialog_id)
        if dialog is None:
            dialog = data.dialogs[-1] if data.dialogs else self._new_dialog(data)
            data.active_dialog_id = dialog.id
        return dialog

    # ---------- чтение ----------
    async def get_state(self, user_id: int) -> tuple[UserData, Dialog]:
        """Данные пользователя и активный диалог (первый диалог создаётся автоматически)."""
        async with self._repo.transaction(user_id) as data:
            dialog = self._ensure_active(data)
            return data.model_copy(deep=True), dialog.model_copy(deep=True)

    # ---------- изменение ----------
    async def create_dialog(self, user_id: int) -> Dialog:
        async with self._repo.transaction(user_id) as data:
            if len(data.dialogs) >= self._max_dialogs:
                raise DialogLimitError(
                    f"Достигнут лимит диалогов ({self._max_dialogs}). "
                    "Удалите ненужный диалог в списке и попробуйте снова."
                )
            data.settings.pending_action = None
            return self._new_dialog(data).model_copy(deep=True)

    async def switch(self, user_id: int, dialog_id: str) -> Dialog:
        async with self._repo.transaction(user_id) as data:
            dialog = self._require(data, dialog_id)
            data.active_dialog_id = dialog.id
            data.settings.pending_action = None
            return dialog.model_copy(deep=True)

    async def delete(self, user_id: int, dialog_id: str) -> Dialog:
        """Удаляет диалог. Возвращает активный диалог после удаления."""
        async with self._repo.transaction(user_id) as data:
            dialog = self._require(data, dialog_id)
            data.dialogs.remove(dialog)
            data.settings.pending_action = None
            if data.get_dialog(data.active_dialog_id) is None:
                active = data.dialogs[-1] if data.dialogs else self._new_dialog(data)
                data.active_dialog_id = active.id
            return self._require(data, data.active_dialog_id).model_copy(deep=True)

    async def begin_rename(self, user_id: int) -> Dialog:
        async with self._repo.transaction(user_id) as data:
            dialog = self._ensure_active(data)
            data.settings.pending_action = PendingAction.RENAME_DIALOG
            return dialog.model_copy(deep=True)

    async def cancel_pending(self, user_id: int) -> None:
        async with self._repo.transaction(user_id) as data:
            data.settings.pending_action = None

    async def rename_active(self, user_id: int, raw_title: str) -> Dialog:
        title = normalize_title(raw_title)
        if not title:
            raise BotError("Название не может быть пустым. Напишите новое название текстом.")
        async with self._repo.transaction(user_id) as data:
            dialog = self._ensure_active(data)
            dialog.title, dialog.title_is_auto = title, False
            data.settings.pending_action = None
            return dialog.model_copy(deep=True)

    async def set_role(self, user_id: int, role_id: str) -> tuple[Dialog, Role]:
        """Меняет роль ТОЛЬКО активного диалога (system prompt берётся из роли при каждом запросе)."""
        if role_id not in ROLES_BY_ID:
            raise BotError("Такого режима нет. Выберите режим кнопкой.")
        async with self._repo.transaction(user_id) as data:
            dialog = self._ensure_active(data)
            dialog.role_id = role_id
            data.settings.pending_action = None
            return dialog.model_copy(deep=True), get_role(role_id)
