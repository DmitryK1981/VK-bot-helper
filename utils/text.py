from __future__ import annotations

VK_MESSAGE_LIMIT = 4096
BUTTON_LABEL_LIMIT = 40


def split_message(text: str, limit: int = 4000) -> list[str]:
    """Делит длинный ответ на части ≤ limit, стараясь резать по абзацам/строкам/пробелам."""
    parts: list[str] = []
    rest = text.strip()
    while len(rest) > limit:
        cut = max(rest.rfind("\n\n", 0, limit), rest.rfind("\n", 0, limit), rest.rfind(" ", 0, limit))
        if cut < limit // 2:
            cut = limit
        parts.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        parts.append(rest)
    return parts or [""]


def shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def shorten_head(text: str, limit: int) -> str:
    """Для превью стриминга: показываем начало, если текст уже не влезает в одно сообщение."""
    return text if len(text) <= limit else text[: limit - 1] + "…"
