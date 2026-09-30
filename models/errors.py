"""Доменные исключения; текст message безопасно показывать пользователю."""


class BotError(Exception):
    """Базовая ошибка бота с понятным пользователю текстом."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


class DialogLimitError(BotError):
    pass


class DialogNotFoundError(BotError):
    pass


class AIServiceError(BotError):
    """Провайдер ИИ недоступен / вернул ошибку (после ретраев и fallback)."""
