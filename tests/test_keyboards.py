import json

from config.roles import ROLES
from keyboards import menus
from keyboards.payloads import Cmd
from models.chat import Dialog


def _parse(raw: str) -> dict:
    kb = json.loads(raw)
    rows = kb["buttons"]
    assert len(rows) <= 10, "VK: не более 10 строк"
    assert sum(len(r) for r in rows) <= 40, "VK: не более 40 кнопок"
    for row in rows:
        assert 1 <= len(row) <= 5
        for b in row:
            assert len(b["action"]["label"]) <= 40, "VK: подпись кнопки до 40 символов"
    return kb


def _payload(button: dict) -> dict:
    raw = button["action"]["payload"]  # vkbottle кладёт payload вложенным объектом
    return json.loads(raw) if isinstance(raw, str) else raw


def _cmds(kb: dict) -> list[str]:
    return [_payload(b)["cmd"] for row in kb["buttons"] for b in row]


def test_main_menu_has_all_required_buttons():
    kb = _parse(menus.main_menu())
    labels = [b["action"]["label"] for row in kb["buttons"] for b in row]
    for word in ("Новый диалог", "Список диалогов", "Настройки", "Сменить режим", "Помощь"):
        assert any(word in label for label in labels), word
    assert kb["inline"] is False


def test_dialog_list_fits_vk_limits_with_max_dialogs_and_long_titles():
    dialogs = [Dialog(title="Очень длинное название диалога" * 3) for _ in range(8)]
    kb = _parse(menus.dialogs_list(dialogs, dialogs[0].id))
    cmds = _cmds(kb)
    assert cmds.count(Cmd.SWITCH) == 8 and cmds.count(Cmd.DELETE_ASK) == 8
    assert Cmd.DELETE not in cmds  # прямого удаления в списке нет — только через подтверждение


def test_roles_menu_lists_all_five_roles():
    kb = _parse(menus.roles_menu("teacher"))
    assert _cmds(kb).count(Cmd.SET_ROLE) == len(ROLES) == 5


def test_confirm_delete_carries_dialog_id():
    kb = _parse(menus.confirm_delete("abc123"))
    payloads = [_payload(b) for row in kb["buttons"] for b in row]
    assert {"cmd": Cmd.DELETE, "id": "abc123"} in payloads


def test_settings_and_confirm_clear():
    _parse(menus.settings_menu())
    assert Cmd.CLEAR_YES in _cmds(_parse(menus.confirm_clear()))
    assert Cmd.CANCEL in _cmds(_parse(menus.cancel_only()))
