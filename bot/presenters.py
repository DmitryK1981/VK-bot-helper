"""Тексты сообщений бота (вся русская локализация — здесь и в handlers)."""
from __future__ import annotations

from config.roles import get_role
from models.chat import Dialog

HELP_TEXT = (
    "❓ Как пользоваться ботом\n\n"
    "Просто напишите сообщение — я отвечу с помощью нейросети и запомню контекст разговора "
    "(последние 100 сообщений диалога).\n\n"
    "➕ Новый диалог — начать разговор «с чистого листа». Диалоги независимы друг от друга.\n"
    "💬 Список диалогов — переключаться между диалогами и удалять ненужные.\n"
    "🎭 Сменить режим — задать стиль общения (программист, преподаватель и т. д.). "
    "Режим действует только в текущем диалоге.\n"
    "⚙️ Настройки — переименовать диалог, очистить историю, узнать модель.\n\n"
    "Если что-то пошло не так, нажмите «⬅️ В меню» или напишите «меню»."
)


def dialog_card(dialog: Dialog) -> str:
    role = get_role(dialog.role_id)
    return (
        f"💬 Диалог: «{dialog.title}»\n"
        f"🎭 Режим: {role.label}\n"
        f"🧠 В памяти сообщений: {len(dialog.messages)}"
    )


def dialogs_overview(dialogs: list[Dialog], active_id: str | None, limit: int) -> str:
    lines = [f"💬 Ваши диалоги ({len(dialogs)} из {limit}):", ""]
    for n, d in enumerate(dialogs, start=1):
        mark = "✅" if d.id == active_id else "▫️"
        lines.append(f"{mark} {n}. {d.title} — {get_role(d.role_id).label}, сообщений: {len(d.messages)}")
    lines += ["", "Нажмите на название, чтобы переключиться, или «🗑 Удалить» с нужным номером."]
    return "\n".join(lines)
