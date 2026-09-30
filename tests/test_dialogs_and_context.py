import pytest

from config.roles import ROLES, get_role
from models.chat import MessageRole
from models.errors import AIServiceError, BotError, DialogLimitError, DialogNotFoundError
from tests.conftest import make_world

UID = 42


async def test_first_dialog_autocreated(world):
    _, d = await world.dialogs.get_state(UID)
    assert d.title == "Диалог 1" and (world.repo._dir / "42.json").exists()


def test_five_roles_defined():
    assert len(ROLES) == 5 and len({r.id for r in ROLES}) == 5
    assert all(r.system_prompt for r in ROLES)
    assert get_role("нет-такой").id == "assistant"


async def test_context_has_system_history_and_new_user_message(world):
    await world.chat.answer(UID, "Привет")
    await world.chat.answer(UID, "Как дела?")
    messages, _ = world.provider.calls[-1]
    assert messages[0].role is MessageRole.SYSTEM
    assert messages[0].content == get_role("assistant").system_prompt
    assert [m.role.value for m in messages[1:]] == ["user", "assistant", "user"]
    assert messages[-1].content == "Как дела?"


async def test_role_change_affects_only_active_dialog(world):
    _, d1 = await world.dialogs.get_state(UID)
    await world.dialogs.set_role(UID, "programmer")
    d2 = await world.dialogs.create_dialog(UID)
    await world.chat.answer(UID, "во втором")
    assert world.provider.calls[-1][0][0].content == get_role("assistant").system_prompt
    await world.dialogs.switch(UID, d1.id)
    await world.chat.answer(UID, "в первом")
    assert world.provider.calls[-1][0][0].content == get_role("programmer").system_prompt
    assert d2.id != d1.id


async def test_switching_changes_history(world):
    _, d1 = await world.dialogs.get_state(UID)
    await world.chat.answer(UID, "один")
    await world.dialogs.create_dialog(UID)
    await world.chat.answer(UID, "два")
    assert len(world.provider.calls[-1][0]) == 2  # только system + новое сообщение
    await world.dialogs.switch(UID, d1.id)
    await world.chat.answer(UID, "снова один")
    assert len(world.provider.calls[-1][0]) == 4


async def test_invalid_role_rejected(world):
    with pytest.raises(BotError):
        await world.dialogs.set_role(UID, "hacker")


async def test_rename_normalizes_and_rejects_empty(world):
    await world.dialogs.get_state(UID)
    assert (await world.dialogs.rename_active(UID, "  Мой   чат ")).title == "Мой чат"
    assert len((await world.dialogs.rename_active(UID, "x" * 100)).title) == 30
    with pytest.raises(BotError):
        await world.dialogs.rename_active(UID, "   ")


async def test_auto_title_from_first_message_but_not_after_manual_rename(world):
    await world.chat.answer(UID, "Расскажи про космос")
    _, d = await world.dialogs.get_state(UID)
    assert d.title == "Расскажи про космос"
    await world.dialogs.rename_active(UID, "Космос")
    await world.chat.answer(UID, "ещё")
    _, d = await world.dialogs.get_state(UID)
    assert d.title == "Космос"


async def test_dialog_limit_and_delete(world):
    await world.dialogs.get_state(UID)
    await world.dialogs.create_dialog(UID)
    await world.dialogs.create_dialog(UID)
    with pytest.raises(DialogLimitError):
        await world.dialogs.create_dialog(UID)
    _, active = await world.dialogs.get_state(UID)
    after = await world.dialogs.delete(UID, active.id)
    assert after.id != active.id
    with pytest.raises(DialogNotFoundError):
        await world.dialogs.delete(UID, active.id)


async def test_deleting_last_dialog_creates_new_one(world):
    _, d = await world.dialogs.get_state(UID)
    new = await world.dialogs.delete(UID, d.id)
    assert new.id != d.id and new.messages == []


async def test_history_window_is_100_when_summary_unavailable(tmp_path):
    w = make_world(tmp_path, max_messages=100, batch=20)
    w.provider.summary_fails = True
    for i in range(60):
        await w.chat.answer(UID, f"m{i}")
        await w.chat.wait_background()
    _, d = await w.dialogs.get_state(UID)
    assert len(d.messages) <= 100
    assert d.messages[-2].content == "m59"


async def test_validation(world):
    for bad in ("", "   ", None, "x" * 201):
        with pytest.raises(BotError):
            await world.chat.answer(UID, bad)
    assert world.provider.calls == []


async def test_fallback_model_and_total_failure_not_saved(world):
    world.provider.fail_models = {None}
    assert (await world.chat.answer(UID, "q")).startswith("ответ")
    assert world.provider.calls[-1][1] == "backup"
    world.provider.fail_models = {None, "backup"}
    with pytest.raises(AIServiceError):
        await world.chat.answer(UID, "потерян")
    _, d = await world.dialogs.get_state(UID)
    assert all(m.content != "потерян" for m in d.messages)


async def test_retry_on_transient_error(world):
    world.provider.transient_errors = 2
    assert (await world.chat.answer(UID, "q")).startswith("ответ")
    assert len(world.provider.calls) == 3


async def test_clear_history_removes_messages_and_summary(world):
    await world.chat.answer(UID, "q")
    async with world.repo.transaction(UID) as data:
        data.dialogs[0].summary = "что-то"
    await world.memory.clear(UID)
    _, d = await world.dialogs.get_state(UID)
    assert d.messages == [] and d.summary == ""
