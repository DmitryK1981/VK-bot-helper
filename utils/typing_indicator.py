from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import AsyncIterator

from vkbottle.api import API

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def typing_indicator(api: API, peer_id: int, interval: float = 4.0) -> AsyncIterator[None]:
    """Показывает «печатает…» в чате, пока выполняется блок (VK гасит статус через ~5 c)."""

    async def _loop() -> None:
        while True:
            try:
                await api.messages.set_activity(peer_id=peer_id, type="typing")
            except Exception:  # индикатор — мелочь, сбой не должен ломать ответ
                logger.debug("Не удалось отправить статус typing", exc_info=True)
            await asyncio.sleep(interval)

    task = asyncio.create_task(_loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
