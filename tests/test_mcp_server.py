import importlib
import sys
from pathlib import Path

import pytest

VALID_KEY = "a" * 32
MCP_SERVER_DIR = Path(__file__).resolve().parent.parent / "mcp-server"
sys.path.insert(0, str(MCP_SERVER_DIR))


@pytest.fixture
def crossbot_mcp(live_crossbot_server, monkeypatch):
    """Laedt crossbot_mcp.py mit Config passend zum laufenden Test-Server neu."""
    monkeypatch.setenv("CROSSBOT_API_URL", f"http://127.0.0.1:{live_crossbot_server}")
    monkeypatch.setenv("CROSSBOT_API_KEY", VALID_KEY)

    if "crossbot_mcp" in sys.modules:
        return importlib.reload(sys.modules["crossbot_mcp"])
    return importlib.import_module("crossbot_mcp")


def test_send_and_pending(crossbot_mcp):
    r = crossbot_mcp.crossbot_send(from_bot="eddie", to_bot="marvin", body="hi")
    assert r["status"] == "pending"

    r = crossbot_mcp.crossbot_pending(bot_name="marvin")
    assert len(r["messages"]) == 1
    assert r["messages"][0]["body"] == "hi"


def test_respond_and_status(crossbot_mcp):
    msg_id = crossbot_mcp.crossbot_send(from_bot="eddie", to_bot="marvin", body="hi")["id"]
    r = crossbot_mcp.crossbot_respond(msg_id=msg_id, response_text="ok")
    assert r["status"] == "done"

    r = crossbot_mcp.crossbot_status(msg_id=msg_id)
    assert r["response_text"] == "ok"


def test_cancel(crossbot_mcp):
    msg_id = crossbot_mcp.crossbot_send(from_bot="eddie", to_bot="marvin", body="hi")["id"]
    r = crossbot_mcp.crossbot_cancel(msg_id=msg_id)
    assert r["status"] == "cancelled"


def test_bot_registry_and_broadcast(crossbot_mcp):
    crossbot_mcp.crossbot_register_bot(name="eddie")
    crossbot_mcp.crossbot_register_bot(name="marvin")

    bots = crossbot_mcp.crossbot_list_bots()["bots"]
    assert {b["name"] for b in bots} == {"eddie", "marvin"}

    crossbot_mcp.crossbot_group_add(group="ops", bot="eddie")
    crossbot_mcp.crossbot_group_add(group="ops", bot="marvin")
    assert crossbot_mcp.crossbot_list_groups()["groups"] == ["ops"]
    assert crossbot_mcp.crossbot_group_members(group="ops")["members"] == ["eddie", "marvin"]

    r = crossbot_mcp.crossbot_broadcast(from_bot="eddie", to_group="ops", body="achtung")
    assert len(r["ids"]) == 2

    crossbot_mcp.crossbot_group_remove(group="ops", bot="marvin")
    assert crossbot_mcp.crossbot_group_members(group="ops")["members"] == ["eddie"]

    crossbot_mcp.crossbot_revoke_bot(name="marvin")
    assert {b["name"] for b in crossbot_mcp.crossbot_list_bots()["bots"]} == {"eddie"}


def test_error_surfaces_as_exception_not_exit(crossbot_mcp):
    with pytest.raises(RuntimeError, match="404"):
        crossbot_mcp.crossbot_status(msg_id=999999)
