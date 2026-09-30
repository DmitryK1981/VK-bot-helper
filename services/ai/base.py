"""Абстракция LLM-провайдера. AIService зависит только от неё, а не от Gemini."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

from models.chat import MessageRole


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: MessageRole
    content: str


class ProviderError(Exception):
    """Ошибка провайдера. retryable=True — имеет смысл повторить запрос."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMProvider(ABC):
    @property
    @abstractmethod
    def default_model(self) -> str: ...

    @abstractmethod
    async def generate(self, messages: list[LLMMessage], *, model: str | None = None) -> str:
        """messages: [system?, ...user/assistant..., user]. Возвращает текст ответа."""

    @abstractmethod
    def stream(self, messages: list[LLMMessage], *, model: str | None = None) -> AsyncIterator[str]:
        """Потоковая генерация: выдаёт фрагменты текста (дельты) по мере появления."""

    async def close(self) -> None:  # noqa: B027 - необязательный хук
        """Освобождение ресурсов."""
