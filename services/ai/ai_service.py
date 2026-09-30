"""AIService — единая точка работы с ИИ: контекст, стриминг, ретраи, fallback-модель, суммаризация."""
from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator

from models.chat import ChatMessage, MessageRole
from models.errors import AIServiceError
from services.ai.base import LLMMessage, LLMProvider, ProviderError

logger = logging.getLogger(__name__)

_USER_FACING_ERROR = "😔 Не удалось получить ответ от нейросети. Попробуйте повторить запрос чуть позже."

_SUMMARY_SYSTEM_PROMPT = (
    "Ты помогаешь боту сохранять память о разговоре. Объедини прежнее краткое содержание и новые "
    "реплики в одно связное краткое содержание на русском языке. Сохрани важные факты о пользователе, "
    "его цели, договорённости, принятые решения и незавершённые вопросы; опусти приветствия и мелочи. "
    "Пиши от третьего лица, без вступлений, максимум {limit} символов."
)


class AIService:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        fallback_model: str | None = None,
        max_retries: int = 2,
        retry_base_delay: float = 1.0,
    ) -> None:
        self._provider = provider
        self._fallback_model = fallback_model or None
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay

    @property
    def model_name(self) -> str:
        return self._provider.default_model

    # ---------- контекст ----------
    @staticmethod
    def build_context(
        system_prompt: str, history: list[ChatMessage], user_text: str, limit: int
    ) -> list[LLMMessage]:
        """system + последние `limit` сообщений истории + новое сообщение пользователя."""
        recent = history[-limit:]
        # Диалог для модели должен начинаться с реплики пользователя
        while recent and recent[0].role is not MessageRole.USER:
            recent = recent[1:]
        return [
            LLMMessage(MessageRole.SYSTEM, system_prompt),
            *(LLMMessage(m.role, m.content) for m in recent if m.role is not MessageRole.SYSTEM),
            LLMMessage(MessageRole.USER, user_text),
        ]

    # ---------- публичное API ----------
    async def reply(
        self, system_prompt: str, history: list[ChatMessage], user_text: str, *, history_limit: int
    ) -> str:
        """Ответ целиком (без стриминга)."""
        messages = self.build_context(system_prompt, history, user_text, history_limit)
        return await self._with_fallback(lambda model: self._generate_with_retries(messages, model))

    async def reply_stream(
        self, system_prompt: str, history: list[ChatMessage], user_text: str, *, history_limit: int
    ) -> AsyncIterator[str]:
        """Ответ потоком фрагментов. Ретраи/fallback возможны только до первого фрагмента."""
        messages = self.build_context(system_prompt, history, user_text, history_limit)
        models = self._models_to_try()
        last_error: ProviderError | None = None
        for model in models:
            attempt = 0
            while True:
                produced = False
                try:
                    async for delta in self._provider.stream(messages, model=model):
                        produced = True
                        yield delta
                    return
                except ProviderError as exc:
                    last_error = exc
                    if produced:  # текст уже показан пользователю — переиграть нельзя
                        logger.warning("Поток оборван после частичного ответа: %s", exc)
                        raise AIServiceError(_USER_FACING_ERROR) from exc
                    if exc.retryable and attempt < self._max_retries:
                        attempt += 1
                        await self._backoff(attempt, exc)
                        continue
                    logger.warning("Модель %s не ответила: %s", model or self.model_name, exc)
                    break
        raise AIServiceError(_USER_FACING_ERROR) from last_error

    async def summarize(self, previous_summary: str, messages: list[ChatMessage], *, max_chars: int) -> str:
        """Сворачивает старые сообщения (и прежнее резюме) в краткое содержание."""
        transcript = "\n".join(
            f"{'Пользователь' if m.role is MessageRole.USER else 'Ассистент'}: {m.content}" for m in messages
        )
        prompt = (
            f"Прежнее краткое содержание:\n{previous_summary or '(пусто)'}\n\n"
            f"Новые реплики:\n{transcript}\n\nОбновлённое краткое содержание:"
        )
        request = [
            LLMMessage(MessageRole.SYSTEM, _SUMMARY_SYSTEM_PROMPT.format(limit=max_chars)),
            LLMMessage(MessageRole.USER, prompt),
        ]
        text = await self._with_fallback(lambda model: self._generate_with_retries(request, model))
        return text[:max_chars].strip()

    # ---------- внутреннее ----------
    def _models_to_try(self) -> list[str | None]:
        models: list[str | None] = [None]  # None = модель по умолчанию
        if self._fallback_model and self._fallback_model != self.model_name:
            models.append(self._fallback_model)
        return models

    async def _with_fallback(self, call) -> str:  # type: ignore[no-untyped-def]
        last_error: ProviderError | None = None
        for model in self._models_to_try():
            try:
                return await call(model)
            except ProviderError as exc:
                last_error = exc
                logger.warning("Модель %s не ответила: %s", model or self.model_name, exc)
        raise AIServiceError(_USER_FACING_ERROR) from last_error

    async def _generate_with_retries(self, messages: list[LLMMessage], model: str | None) -> str:
        attempt = 0
        while True:
            try:
                return await self._provider.generate(messages, model=model)
            except ProviderError as exc:
                if not exc.retryable or attempt >= self._max_retries:
                    raise
                attempt += 1
                await self._backoff(attempt, exc)

    async def _backoff(self, attempt: int, exc: ProviderError) -> None:
        delay = self._retry_base_delay * 2 ** (attempt - 1) + random.random() * self._retry_base_delay
        logger.info("Повтор %d через %.1f c: %s", attempt, delay, exc)
        await asyncio.sleep(delay)

    async def close(self) -> None:
        await self._provider.close()
