"""Сборка приложения (composition root): конфиг → зависимости → VK-бот → запуск."""
from __future__ import annotations

import logging

from vkbottle.bot import Bot, BotLabeler

from bot.container import Container
from bot.handlers import chat, dialogs, menu, settings
from config.settings import get_settings
from services.ai.ai_service import AIService
from services.ai.gemini_provider import GeminiProvider
from services.chat_service import ChatService
from services.dialog_manager import DialogManager
from services.memory_manager import MemoryManager
from services.rate_limiter import RateLimiter
from storage.json_storage import JsonUserRepository
from utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def build_bot() -> Bot:
    cfg = get_settings()
    setup_logging(cfg.log_level)

    repo = JsonUserRepository(cfg.users_dir)
    provider = GeminiProvider(
        api_key=cfg.proxyapi_key.get_secret_value(),
        base_url=cfg.proxyapi_base_url,
        model=cfg.gemini_model,
        temperature=cfg.gemini_temperature,
        max_output_tokens=cfg.gemini_max_output_tokens,
        timeout_seconds=cfg.ai_timeout_seconds,
    )
    ai = AIService(provider, fallback_model=cfg.gemini_fallback_model, max_retries=cfg.ai_max_retries)
    dialog_manager = DialogManager(repo, cfg.max_dialogs_per_user)
    memory = MemoryManager(repo, cfg.max_history_messages, cfg.summary_batch_size)
    container = Container(
        dialogs=dialog_manager,
        memory=memory,
        chat=ChatService(
            dialog_manager,
            memory,
            ai,
            RateLimiter(cfg.rate_limit_requests, cfg.rate_limit_window_seconds),
            max_message_length=cfg.max_user_message_length,
            summary_max_chars=cfg.summary_max_chars,
        ),
        max_dialogs=cfg.max_dialogs_per_user,
    )

    labeler = BotLabeler()
    # Порядок важен: сначала кнопки/команды, затем «ловящий всё» чат-обработчик
    for module in (menu, dialogs, settings):
        module.register(labeler, container)
    chat.register(labeler, container, edit_interval=cfg.stream_edit_interval)

    bot = Bot(token=cfg.vk_token.get_secret_value(), labeler=labeler)
    bot.on_shutdown.append(ai.close())
    logger.info("Бот собран. Модель: %s", ai.model_name)
    return bot


def main() -> None:
    build_bot().run()


if __name__ == "__main__":
    main()
