"""Сценарии на уровне VK-обработчиков: настоящие handlers + имитация сообщений VK."""
import pytest

from bot.handlers import chat, dialogs, menu, settings
from keyboards.payloads import Cmd
from tests.conftest import FakeLabeler, FakeMessage, button, make_world

UID = 1


@pytest.fixture
def bot(tmp_path):
    w = make_world(tmp_path, max_len=200)
    labeler = FakeLabeler()
    for module in (menu, dialogs, settings):
        module.register(labeler, w.container)
    chat.register(labeler, w.container, edit_interval=0)  # правим сообщение на каждом фрагменте
    return w, labeler


async def send(labeler, msg: FakeMessage) -> FakeMessage:
    await labeler.dispatch(msg)
    return msg


def texts(msg: FakeMessage) -> str:
    return "\n".join(t for t, _ in msg.answers)


async def test_menu_commands_case_insensitive(bot):
    _, lb = bot
    for word in ("Меню", "начать", "/start"):
        msg = await send(lb, FakeMessage(word))
        assert "Привет" in texts(msg) and msg.answers[0][1]  # клавиатура прикреплена


async def test_help(bot):
    _, lb = bot
    assert "Как пользоваться" in texts(await send(lb, button(Cmd.HELP)))


async def test_new_dialog_list_switch_delete_flow(bot):
    w, lb = bot
    await send(lb, FakeMessage("привет"))
    m = await send(lb, button(Cmd.NEW))
    assert "Новый диалог создан" in texts(m)
    data, _ = await w.dialogs.get_state(UID)
    assert len(data.dialogs) == 2
    first, second = data.dialogs

    m = await send(lb, button(Cmd.LIST))
    assert "Ваши диалоги (2 из 3)" in texts(m)

    m = await send(lb, button(Cmd.SWITCH, id=first.id))
    assert "Переключено" in texts(m)
    assert (await w.dialogs.get_state(UID))[1].id == first.id

    m = await send(lb, button(Cmd.DELETE_ASK, id=second.id))  # сначала подтверждение
    assert "Удалить диалог" in texts(m)
    assert len((await w.dialogs.get_state(UID))[0].dialogs) == 2  # ещё не удалён

    m = await send(lb, button(Cmd.DELETE, id=second.id))
    assert "Диалог удалён" in texts(m)
    assert len((await w.dialogs.get_state(UID))[0].dialogs) == 1


async def test_delete_ask_for_missing_dialog(bot):
    _, lb = bot
    assert "уже нет" in texts(await send(lb, button(Cmd.DELETE_ASK, id="nope")))


async def test_dialog_limit_message(bot):
    _, lb = bot
    for _ in range(3):  # лимит в тестовой конфигурации — 3 диалога
        await send(lb, button(Cmd.NEW))
    assert "лимит" in texts(await send(lb, button(Cmd.NEW))).lower()


async def test_role_switch_flow(bot):
    w, lb = bot
    m = await send(lb, button(Cmd.ROLES))
    assert "Программист" in texts(m) and "Преподаватель" in texts(m)
    m = await send(lb, button(Cmd.SET_ROLE, id="teacher"))
    assert "Режим изменён" in texts(m)
    assert (await w.dialogs.get_state(UID))[1].role_id == "teacher"
    m = await send(lb, button(Cmd.SET_ROLE, id="bad"))
    assert "Такого режима нет" in texts(m)


async def test_settings_screen_shows_model(bot):
    _, lb = bot
    assert "Модель: main" in texts(await send(lb, button(Cmd.SETTINGS)))


async def test_rename_flow_uses_next_text_message(bot):
    w, lb = bot
    m = await send(lb, button(Cmd.RENAME))
    assert "Напишите новое название" in texts(m)
    m = await send(lb, FakeMessage("Мой проект"))
    assert "переименован" in texts(m)
    assert (await w.dialogs.get_state(UID))[1].title == "Мой проект"
    assert w.provider.calls == []  # название не ушло в нейросеть


async def test_rename_cancel(bot):
    w, lb = bot
    await send(lb, button(Cmd.RENAME))
    await send(lb, button(Cmd.CANCEL))
    m = await send(lb, FakeMessage("обычный вопрос"))
    assert w.provider.calls  # снова обычный чат


async def test_clear_history_flow(bot):
    w, lb = bot
    await send(lb, FakeMessage("вопрос"))
    assert "Очистить историю" in texts(await send(lb, button(Cmd.CLEAR_ASK)))
    assert (await w.dialogs.get_state(UID))[1].messages  # пока не очищено
    assert "История очищена" in texts(await send(lb, button(Cmd.CLEAR_YES)))
    assert (await w.dialogs.get_state(UID))[1].messages == []


async def test_chat_shows_thinking_then_streams_and_finalizes(bot):
    _, lb = bot
    msg = await send(lb, FakeMessage("расскажи про космос пожалуйста"))
    assert msg.answers[0][0] == "🤔 Бот думает..."
    edits = msg.api.edits
    assert any(e["message"].endswith("▌") for e in edits[:-1])  # промежуточные правки с курсором
    assert edits[-1]["message"] == "ответ на «расскажи про космос пожалуйста»"
    assert edits[-1]["keyboard"]  # к финальному ответу возвращается меню
    assert msg.api.activities  # статус «печатает…»


async def test_empty_message_rejected_without_thinking(bot):
    w, lb = bot
    for empty in ("", "   ", None):
        msg = await send(lb, FakeMessage(empty))
        assert "пустые сообщения" in texts(msg) and len(msg.answers) == 1
    assert w.provider.calls == []


async def test_too_long_message_rejected(bot):
    _, lb = bot
    assert "слишком длинное" in texts(await send(lb, FakeMessage("я" * 201)))


async def test_ai_failure_shows_friendly_message(bot):
    w, lb = bot
    w.provider.fail_models = {None, "backup"}
    msg = await send(lb, FakeMessage("вопрос"))
    assert "Не удалось получить ответ" in msg.api.edits[-1]["message"]


async def test_midstream_failure_keeps_partial_text(bot):
    w, lb = bot
    w.provider.stream_break_at = 2
    msg = await send(lb, FakeMessage("один два три четыре"))
    final = msg.api.edits[-1]["message"]
    assert final.startswith("ответ на") and "Не удалось получить ответ" in final


async def test_long_reply_is_split_into_multiple_messages(tmp_path):
    w = make_world(tmp_path, max_len=10_000)
    lb = FakeLabeler()
    chat.register(lb, w.container, edit_interval=999)
    msg = await send(lb, FakeMessage("слово " * 1500))  # ответ эхом > 4096 символов
    assert len(msg.answers) >= 2  # заглушка + продолжение
    assert all(len(t) <= 4096 for t, _ in msg.answers) and len(msg.api.edits[-1]["message"]) <= 4096


async def test_rate_limit_message(tmp_path):
    w = make_world(tmp_path, rate=2, window=60)
    lb = FakeLabeler()
    chat.register(lb, w.container, edit_interval=999)
    for _ in range(2):
        await send(lb, FakeMessage("ок"))
    msg = await send(lb, FakeMessage("ещё"))
    assert "Слишком много запросов" in texts(msg) and len(msg.answers) == 1


async def test_failed_edit_falls_back_to_new_message(bot):
    _, lb = bot
    msg = FakeMessage("привет")

    async def broken_edit(**kw):
        raise RuntimeError("VK error")

    msg.api.edit = broken_edit
    await send(lb, msg)
    assert msg.answers[-1][0] == "ответ на «привет»"


async def test_users_do_not_share_state(bot):
    w, lb = bot
    await send(lb, FakeMessage("пользователь один", from_id=1))
    await send(lb, FakeMessage("пользователь два", from_id=2))
    assert (await w.dialogs.get_state(1))[1].messages[0].content == "пользователь один"
    assert (await w.dialogs.get_state(2))[1].messages[0].content == "пользователь два"
