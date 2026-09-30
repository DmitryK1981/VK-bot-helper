"""Общие фикстуры: подставной LLM, сервисы на временном хранилище, имитация VK-сообщения."""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from bot.container import Container
from models.chat import MessageRole
from services.ai.ai_service import AIService
from services.ai.base import LLMMessage, LLMProvider, ProviderError
from services.chat_service import ChatService
from services.dialog_manager import DialogManager
from services.memory_manager import MemoryManager
from services.rate_limiter import RateLimiter
from storage.json_storage import JsonUserRepository

SUMMARY_MARK = "Ты помогаешь боту сохранять память"


class FakeProvider(LLMProvider):
    """Управляемый подставной провайдер.

    fail_models      — модели, которые всегда падают (не retryable);
    transient_errors — сколько первых вызовов упадёт retryable-ошибкой;
    stream_break_at  — после скольких чанков оборвать поток (None = не обрывать).
    """

    def __init__(self) -> None:
        self.calls: list[tuple[list[LLMMessage], str | None]] = []
        self.fail_models: set[str | None] = set()
        self.transient_errors = 0
        self.stream_break_at: int | None = None
        self.summary_fails = False

    @property
    def default_model(self) -> str:
        return "main"

    def _is_summary(self, messages: list[LLMMessage]) -> bool:
        return messages[0].role is MessageRole.SYSTEM and messages[0].content.startswith(SUMMARY_MARK)

    def _check(self, messages: list[LLMMessage], model: str | None) -> None:
        self.calls.append((messages, model))
        if self._is_summary(messages) and self.summary_fails:
            raise ProviderError("summary down")
        if self.transient_errors > 0:
            self.transient_errors -= 1
            raise ProviderError("temporary", retryable=True)
        if model in self.fail_models:
            raise ProviderError("boom")

    def _text(self, messages: list[LLMMessage]) -> str:
        return "РЕЗЮМЕ" if self._is_summary(messages) else f"ответ на «{messages[-1].content}»"

    async def generate(self, messages, *, model=None):
        self._check(messages, model)
        return self._text(messages)

    async def stream(self, messages, *, model=None) -> AsyncIterator[str]:
        self._check(messages, model)
        words = self._text(messages).split(" ")
        for i, word in enumerate(words):
            if self.stream_break_at is not None and i >= self.stream_break_at:
                raise ProviderError("оборвано", retryable=True)
            yield word if i == 0 else " " + word


@dataclass
class World:
    repo: JsonUserRepository
    provider: FakeProvider
    ai: AIService
    dialogs: DialogManager
    memory: MemoryManager
    chat: ChatService
    container: Container


def make_world(tmp_path, *, max_messages=100, batch=20, rate=1000, window=60.0, max_dialogs=3,
               max_len=200, fallback="backup", retries=2) -> World:
    repo = JsonUserRepository(tmp_path)
    provider = FakeProvider()
    ai = AIService(provider, fallback_model=fallback, max_retries=retries, retry_base_delay=0)
    dialogs = DialogManager(repo, max_dialogs)
    memory = MemoryManager(repo, max_messages, batch)
    chat = ChatService(dialogs, memory, ai, RateLimiter(rate, window), max_message_length=max_len)
    return World(repo, provider, ai, dialogs, memory, chat, Container(dialogs, memory, chat, max_dialogs))


@pytest.fixture
def world(tmp_path) -> World:
    return make_world(tmp_path)


# ---------- имитация VK ----------
@dataclass
class FakeApi:
    edits: list[dict] = field(default_factory=list)
    activities: list[dict] = field(default_factory=list)

    async def edit(self, **kw):
        self.edits.append(kw)

    async def set_activity(self, **kw):
        self.activities.append(kw)


class FakeMessage:
    _cmid = 0

    def __init__(self, text: str | None = None, *, from_id: int = 1, payload: dict | None = None) -> None:
        self.text = text
        self.from_id = from_id
        self.peer_id = from_id
        self.payload = payload
        self.answers: list[tuple[str, str | None]] = []
        self.api = FakeApi()
        self.ctx_api = SimpleNamespace(messages=self.api)

    def get_payload_json(self):
        return self.payload

    async def answer(self, message=None, keyboard=None, **kw):
        self.answers.append((message or "", keyboard))
        FakeMessage._cmid += 1
        return SimpleNamespace(conversation_message_id=FakeMessage._cmid)


class FakeLabeler:
    """Собирает зарегистрированные обработчики и умеет «доставлять» им сообщения по правилам."""

    def __init__(self) -> None:
        self.handlers: list[tuple[tuple, object]] = []

    def private_message(self, *rules, **kwargs):
        def decorator(func):
            self.handlers.append((rules, func))
            return func

        return decorator

    async def dispatch(self, message: FakeMessage) -> None:
        for rules, func in self.handlers:
            if all([await rule.check(message) for rule in rules]):
                await func(message)
                return
        raise AssertionError("ни один обработчик не подошёл")


def button(cmd: str, **args) -> FakeMessage:
    return FakeMessage(payload={"cmd": cmd, **args})
