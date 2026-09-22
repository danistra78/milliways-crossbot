import importlib
import socket
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn

VALID_KEY = "a" * 32
MCP_SERVER_DIR = Path(__file__).resolve().parent.parent / "mcp-server"
sys.path.insert(0, str(MCP_SERVER_DIR))


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _ServerThread(threading.Thread):
    def __init__(self, app, host: str, port: int):
        super().__init__(daemon=True)
        self.server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True


@pytest.fixture
def crossbot_mcp(crossbot_env, monkeypatch):
    """Startet main.py als echten HTTP-Server (Bot-Key-Auth braucht mehrere
    unabhaengige Requests) und laedt crossbot_mcp.py mit passender Config neu."""
    port = _free_port()
    thread = _ServerThread(crossbot_env.app, "127.0.0.1", port)
    thread.start()
    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.05)
    else:
        raise RuntimeError("Test-Server nicht hochgekommen")

    monkeypatch.setenv("CROSSBOT_API_URL", f"http://127.0.0.1:{port}")
    monkeypatch.setenv("CROSSBOT_API_KEY", VALID_KEY)

    if "crossbot_mcp" in sys.modules:
        module = importlib.reload(sys.modules["crossbot_mcp"])
    else:
        module = importlib.import_module("crossbot_mcp")

    try:
        yield module
    finally:
        thread.stop()
        thread.join(timeout=5)


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
