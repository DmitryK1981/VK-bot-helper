import asyncio
import json

from models.chat import ChatMessage, Dialog, MessageRole
from storage.json_storage import JsonUserRepository


async def test_file_created_on_read(tmp_path):
    repo = JsonUserRepository(tmp_path)
    data = await repo.read(7)
    assert data.user_id == 7 and (tmp_path / "7.json").exists()


async def test_transaction_persists_and_leaves_no_tmp(tmp_path):
    repo = JsonUserRepository(tmp_path)
    async with repo.transaction(7) as data:
        data.active_dialog_id = "abc"
    assert json.loads((tmp_path / "7.json").read_text(encoding="utf-8"))["active_dialog_id"] == "abc"
    assert not list(tmp_path.glob("*.tmp"))


async def test_exception_in_transaction_does_not_save(tmp_path):
    repo = JsonUserRepository(tmp_path)
    try:
        async with repo.transaction(7) as data:
            data.active_dialog_id = "zzz"
            raise RuntimeError
    except RuntimeError:
        pass
    assert (await repo.read(7)).active_dialog_id is None


async def test_concurrent_transactions_lose_no_updates(tmp_path):
    repo = JsonUserRepository(tmp_path)
    async with repo.transaction(1) as data:
        data.dialogs.append(Dialog(title="d"))

    async def add(i: int) -> None:
        async with repo.transaction(1) as data:
            data.dialogs[0].messages.append(ChatMessage(role=MessageRole.USER, content=str(i)))

    await asyncio.gather(*(add(i) for i in range(50)))
    assert len((await repo.read(1)).dialogs[0].messages) == 50


async def test_corrupt_file_is_backed_up(tmp_path):
    (tmp_path / "5.json").write_text("{не json", encoding="utf-8")
    repo = JsonUserRepository(tmp_path)
    data = await repo.read(5)
    assert data.dialogs == []
    assert list(tmp_path.glob("5.corrupt-*.json"))


async def test_users_are_isolated(tmp_path):
    repo = JsonUserRepository(tmp_path)
    async with repo.transaction(1) as d:
        d.active_dialog_id = "a"
    assert (await repo.read(2)).active_dialog_id is None
