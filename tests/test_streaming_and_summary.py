import pytest

from models.errors import AIServiceError, BotError
from tests.conftest import make_world

UID = 1


async def collect(world, text):
    return [d async for d in world.chat.stream_answer(UID, text)]


async def test_stream_yields_chunks_and_saves_full_reply(world):
    chunks = await collect(world, "привет мир")
    assert len(chunks) > 1
    _, d = await world.dialogs.get_state(UID)
    assert d.messages[-1].content == "".join(chunks).strip()


async def test_stream_retries_before_first_chunk(world):
    world.provider.transient_errors = 1
    chunks = await collect(world, "привет")
    assert "".join(chunks).startswith("ответ")
    assert len(world.provider.calls) == 2


async def test_stream_fallback_model(world):
    world.provider.fail_models = {None}
    await collect(world, "привет")
    assert world.provider.calls[-1][1] == "backup"


async def test_stream_break_midway_raises_and_is_not_saved(world):
    world.provider.stream_break_at = 2
    got: list[str] = []
    with pytest.raises(AIServiceError):
        async for d in world.chat.stream_answer(UID, "один два три"):
            got.append(d)
    assert got  # частичный ответ пользователь увидел
    _, d = await world.dialogs.get_state(UID)
    assert d.messages == []
    assert len(world.provider.calls) == 1  # после частичного ответа повторов нет


async def test_busy_and_rate_limit(tmp_path):
    w = make_world(tmp_path, rate=2, window=60)
    assert w.chat.precheck(UID, "a") == "a"
    assert w.chat.precheck(UID, "b") == "b"
    with pytest.raises(BotError, match="Слишком много"):
        w.chat.precheck(UID, "c")
    assert w.chat.precheck(2, "other user") == "other user"
    await w.chat._locks[3].acquire()
    with pytest.raises(BotError, match="отвечаю"):
        w.chat.precheck(3, "x")


async def test_rate_limit_not_consumed_by_invalid_input(tmp_path):
    w = make_world(tmp_path, rate=1, window=60)
    with pytest.raises(BotError):
        w.chat.precheck(UID, "   ")
    assert w.chat.precheck(UID, "ok") == "ok"


async def _fill(w, n, start=0):
    for i in range(start, start + n):
        await w.chat.answer(UID, f"m{i}")
        await w.chat.wait_background()


async def test_old_messages_are_summarized_not_lost(tmp_path):
    w = make_world(tmp_path, max_messages=10, batch=4)
    await _fill(w, 6)  # 12 сообщений > 10 → сворачиваются 12-10+4 = 6 старых
    _, d = await w.dialogs.get_state(UID)
    assert d.summary == "РЕЗЮМЕ"
    assert len(d.messages) == 6 <= 10
    assert d.messages[-2].content == "m5"


async def test_summary_goes_to_system_prompt_and_into_next_summarization(tmp_path):
    w = make_world(tmp_path, max_messages=10, batch=4)
    await _fill(w, 6)
    await w.chat.answer(UID, "после")
    system = w.provider.calls[-1][0][0].content
    assert "РЕЗЮМЕ" in system and "Краткое содержание" in system
    await w.chat.wait_background()
    await _fill(w, 6, start=10)  # ещё одно сворачивание должно получить прежнее резюме
    summary_calls = [m for m, _ in w.provider.calls if m[0].content.startswith("Ты помогаешь боту")]
    assert len(summary_calls) >= 2
    assert "Прежнее краткое содержание:\nРЕЗЮМЕ" in summary_calls[-1][1].content


async def test_summarization_failure_falls_back_to_trimming(tmp_path):
    w = make_world(tmp_path, max_messages=10, batch=4)
    w.provider.summary_fails = True
    await _fill(w, 6)
    _, d = await w.dialogs.get_state(UID)
    assert d.summary == "" and len(d.messages) <= 10


async def test_stale_compaction_plan_is_ignored_after_clear(tmp_path):
    w = make_world(tmp_path, max_messages=4, batch=2)
    _, d = await w.dialogs.get_state(UID)
    for i in range(3):  # копим историю в обход ChatService, чтобы сворачивание не запускалось само
        await w.memory.append_exchange(UID, d.id, f"x{i}", "y")
    job = await w.memory.plan_compaction(UID, d.id)
    assert job is not None and job.count == 4
    await w.memory.clear(UID)
    assert await w.memory.commit_compaction(UID, job, "старое резюме") is False
    _, d = await w.dialogs.get_state(UID)
    assert d.summary == ""
