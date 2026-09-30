"""ChatService связывает диалоги, память и ИИ. Ничего не знает про ВКонтакте."""
from __future__ import annotations

import asyncio
import logging
import math
from collections import defaultdict
from collections.abc import AsyncIterator

from config.roles import get_role
from models.errors import AIServiceError, BotError
from services.ai.ai_service import AIService
from services.dialog_manager import DialogManager
from services.memory_manager import MemoryManager
from services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        dialogs: DialogManager,
        memory: MemoryManager,
        ai: AIService,
        limiter: RateLimiter,
        *,
        max_message_length: int,
        summary_max_chars: int = 1500,
    ) -> None:
        self._dialogs = dialogs
        self._memory = memory
        self._ai = ai
        self._limiter = limiter
        self._max_len = max_message_length
        self._summary_max_chars = summary_max_chars
        self._locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._compacting: set[int] = set()
        self._background: set[asyncio.Task[None]] = set()

    @property
    def model_name(self) -> str:
        return self._ai.model_name

    # ---------- проверки до обращения к модели ----------
    def validate(self, text: str | None) -> str:
        text = (text or "").strip()
        if not text:
            raise BotError("Напишите текстовое сообщение — пустые сообщения я не обрабатываю ✍️")
        if len(text) > self._max_len:
            raise BotError(
                f"Сообщение слишком длинное ({len(text)} симв.). "
                f"Максимум — {self._max_len}. Сократите или разбейте на части."
            )
        return text

    def precheck(self, user_id: int, text: str | None) -> str:
        """Валидация + «уже отвечаю» + лимит частоты. Вызывать перед запуском генерации."""
        text = self.validate(text)
        if self._locks[user_id].locked():
            raise BotError("⏳ Я ещё отвечаю на предыдущее сообщение. Подождите немного.")
        retry_after = self._limiter.acquire(user_id)
        if retry_after > 0:
            raise BotError(
                f"⏳ Слишком много запросов. Подождите {math.ceil(retry_after)} сек. и попробуйте снова."
            )
        return text

    # ---------- генерация ----------
    def _system_prompt(self, role_id: str, summary: str) -> str:
        prompt = get_role(role_id).system_prompt
        if summary:
            prompt += (
                "\n\nКраткое содержание более ранней части этого разговора (используй как контекст, "
                f"не пересказывай без просьбы):\n{summary}"
            )
        return prompt

    async def stream_answer(self, user_id: int, text: str) -> AsyncIterator[str]:
        """Контекст активного диалога → Gemini (поток) → сохранение в память после полного ответа."""
        text = self.validate(text)
        async with self._locks[user_id]:  # сообщения одного пользователя обрабатываются по очереди
            _, dialog = await self._dialogs.get_state(user_id)
            parts: list[str] = []
            async for delta in self._ai.reply_stream(
                self._system_prompt(dialog.role_id, dialog.summary),
                dialog.messages,
                text,
                history_limit=self._memory.max_messages,
            ):
                parts.append(delta)
                yield delta
            reply = "".join(parts).strip()
            await self._memory.append_exchange(user_id, dialog.id, text, reply)
        self._schedule_compaction(user_id, dialog.id)

    async def answer(self, user_id: int, text: str | None) -> str:
        """Ответ целиком (без стриминга) — удобно для тестов и других каналов."""
        return "".join([d async for d in self.stream_answer(user_id, self.validate(text))]).strip()

    # ---------- суммаризация в фоне ----------
    def _schedule_compaction(self, user_id: int, dialog_id: str) -> None:
        if user_id in self._compacting:
            return
        self._compacting.add(user_id)
        task = asyncio.create_task(self._compact(user_id, dialog_id))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _compact(self, user_id: int, dialog_id: str) -> None:
        try:
            job = await self._memory.plan_compaction(user_id, dialog_id)
            if job is None:
                return
            try:
                summary: str | None = await self._ai.summarize(
                    job.previous_summary, job.messages, max_chars=self._summary_max_chars
                )
            except AIServiceError:
                logger.warning("Суммаризация не удалась, старые сообщения отбрасываются (user=%s)", user_id)
                summary = None
            await self._memory.commit_compaction(user_id, job, summary)
        except Exception:
            logger.exception("Ошибка сворачивания истории (user=%s)", user_id)
        finally:
            self._compacting.discard(user_id)

    async def wait_background(self) -> None:
        """Дожидается фоновых задач (для тестов и корректного завершения)."""
        if self._background:
            await asyncio.gather(*self._background, return_exceptions=True)
