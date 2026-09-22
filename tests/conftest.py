import importlib
import os
import sys

import pytest
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
