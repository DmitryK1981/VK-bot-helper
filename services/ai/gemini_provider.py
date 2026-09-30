"""Gemini через ProxyAPI.ru с помощью официального Google GenAI SDK.

ProxyAPI принимает запросы в «родном» формате Google: SDK сам добавляет
/v1beta/models/<model>:generateContent к base_url=https://api.proxyapi.ru
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

import httpx
from google import genai
from google.genai import errors, types

from models.chat import MessageRole
from services.ai.base import LLMMessage, LLMProvider, ProviderError

logger = logging.getLogger(__name__)

_RETRYABLE_HTTP_CODES = {408, 429, 500, 502, 503, 504}


class GeminiProvider(LLMProvider):
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float,
        max_output_tokens: int,
        timeout_seconds: float,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(base_url=base_url, timeout=int(timeout_seconds * 1000)),
        )

    @property
    def default_model(self) -> str:
        return self._model

    @staticmethod
    def _to_contents(messages: list[LLMMessage]) -> tuple[str | None, list[types.Content]]:
        """system-сообщения → system_instruction; assistant → role 'model'."""
        system_parts = [m.content for m in messages if m.role is MessageRole.SYSTEM]
        contents = [
            types.Content(
                role="model" if m.role is MessageRole.ASSISTANT else "user",
                parts=[types.Part.from_text(text=m.content)],
            )
            for m in messages
            if m.role is not MessageRole.SYSTEM
        ]
        return ("\n\n".join(system_parts) or None), contents

    def _prepare(
        self, messages: list[LLMMessage]
    ) -> tuple[list[types.Content], types.GenerateContentConfig]:
        system, contents = self._to_contents(messages)
        if not contents:
            raise ProviderError("Пустой запрос к модели")
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self._temperature,
            max_output_tokens=self._max_output_tokens,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        return contents, config

    @staticmethod
    def _wrap(exc: Exception) -> ProviderError:
        if isinstance(exc, errors.APIError):
            return ProviderError(
                f"Gemini API {exc.code}: {exc.message}",
                retryable=exc.code in _RETRYABLE_HTTP_CODES,
            )
        return ProviderError(f"Сетевая ошибка: {exc!r}", retryable=True)

    async def stream(self, messages: list[LLMMessage], *, model: str | None = None) -> AsyncIterator[str]:
        contents, config = self._prepare(messages)
        produced = False
        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=model or self._model, contents=contents, config=config
            )
            async for chunk in stream:
                if chunk.text:
                    produced = True
                    yield chunk.text
        except (errors.APIError, httpx.TransportError, asyncio.TimeoutError, ConnectionError) as exc:
            err = self._wrap(exc)
            err.retryable = err.retryable and not produced  # повтор после частичного ответа задвоил бы текст
            raise err from exc
        if not produced:
            raise ProviderError("Пустой ответ модели")

    async def generate(self, messages: list[LLMMessage], *, model: str | None = None) -> str:
        contents, config = self._prepare(messages)
        try:
            response = await self._client.aio.models.generate_content(
                model=model or self._model, contents=contents, config=config
            )
        except (errors.APIError, httpx.TransportError, asyncio.TimeoutError, ConnectionError) as exc:
            raise self._wrap(exc) from exc

        text = (response.text or "").strip()
        if not text:
            reason = response.candidates[0].finish_reason if response.candidates else "нет кандидатов"
            raise ProviderError(f"Пустой ответ модели (причина: {reason})")
        return text

    async def close(self) -> None:
        await self._client.aio.aclose()
