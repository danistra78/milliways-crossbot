import importlib
import os
import socket
import sys
import threading
import time

import pytest
import uvicorn
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

VALID_KEY = "a" * 32


@pytest.fixture
def crossbot_env(tmp_path, monkeypatch):
    """Setzt eine frische, isolierte Konfiguration und laedt main.py neu,
    damit die modul-globalen Konstanten (DB_PATH, API_KEY, ...) greifen."""
    monkeypatch.setenv("CROSSBOT_API_KEY", VALID_KEY)
    monkeypatch.setenv("CROSSBOT_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CROSSBOT_RETENTION_DAYS", "0")
    monkeypatch.setenv("CROSSBOT_CLEANUP_INTERVAL_SECONDS", "3600")
    if "main" in sys.modules:
        module = importlib.reload(sys.modules["main"])
    else:
        module = importlib.import_module("main")
    return module


@pytest.fixture
def client(crossbot_env):
    with TestClient(crossbot_env.app) as c:
        yield c


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
def live_crossbot_server(crossbot_env):
    """Startet main.py als echten HTTP-Server auf einem freien Port — fuer
    Clients (MCP-Server, Hermes-Plugin), die per urllib/HTTP statt via
    FastAPI-TestClient zugreifen."""
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

    try:
        yield port
    finally:
        thread.stop()
        thread.join(timeout=5)
