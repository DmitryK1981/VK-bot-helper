from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from models.chat import UserData
from storage.base import UserRepository

logger = logging.getLogger(__name__)


class JsonUserRepository(UserRepository):
    """Один JSON-файл на пользователя: users/<user_id>.json.

    - Запись атомарная (tmp-файл + os.replace) — файл не повредится при падении.
    - Ввод-вывод выполняется в потоке (asyncio.to_thread), не блокируя event loop.
    - На каждого пользователя свой asyncio.Lock — исключает гонки чтение→изменение→запись.
    """

    def __init__(self, users_dir: Path) -> None:
        self._dir = users_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _path(self, user_id: int) -> Path:
        return self._dir / f"{int(user_id)}.json"

    # ---- синхронные примитивы (вызываются только через to_thread) ----
    def _load_sync(self, user_id: int) -> UserData:
        path = self._path(user_id)
        if not path.exists():
            return UserData(user_id=user_id)
        try:
            return UserData.model_validate_json(path.read_text(encoding="utf-8"))
        except (ValueError, json.JSONDecodeError):
            backup = path.with_suffix(f".corrupt-{int(path.stat().st_mtime)}.json")
            logger.exception("Повреждён файл %s, сохраняю копию в %s", path, backup)
            os.replace(path, backup)
            return UserData(user_id=user_id)

    def _save_sync(self, data: UserData) -> None:
        path = self._path(data.user_id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(data.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, path)

    # ---- публичный API ----
    async def read(self, user_id: int) -> UserData:
        data = await asyncio.to_thread(self._load_sync, user_id)
        if not self._path(user_id).exists():
            async with self._locks[user_id]:
                if not self._path(user_id).exists():
                    await asyncio.to_thread(self._save_sync, data)
        return data

    @asynccontextmanager
    async def transaction(self, user_id: int) -> AsyncIterator[UserData]:
        async with self._locks[user_id]:
            data = await asyncio.to_thread(self._load_sync, user_id)
            yield data  # при исключении внутри блока сохранение не происходит
            await asyncio.to_thread(self._save_sync, data)
