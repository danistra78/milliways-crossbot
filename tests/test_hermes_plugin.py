import importlib.util
import json
import sys
from pathlib import Path

import pytest

VALID_KEY = "a" * 32
PLUGIN_DIR = Path(__file__).resolve().parent.parent / "hermes-plugin" / "crossbot"


def _load_plugin(module_name="hermes_crossbot_plugin_under_test"):
    """Laedt das Plugin unter einem eigenen Modulnamen statt es als 'crossbot'
    auf sys.path zu haengen — das wuerde mit dem gleichnamigen crossbot.py
    CLI-Client im Repo-Root kollidieren."""
    for key in [k for k in sys.modules if k == module_name or k.startswith(module_name + ".")]:
        del sys.modules[key]
    spec = importlib.util.spec_from_file_location(
        module_name, PLUGIN_DIR / "__init__.py",
        submodule_search_locations=[str(PLUGIN_DIR)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class _FakeCtx:
    """Minimaler Stand-in fuer Hermes' PluginContext — reicht, um register()
    ohne die echte Hermes-Runtime zu testen."""

    def __init__(self):
        self.registered = {}

    def register_tool(self, *, name, toolset, schema, handler, **kwargs):
        self.registered[name] = {"toolset": toolset, "schema": schema, "handler": handler}


def test_register_wires_all_declared_tools():
    plugin = _load_plugin()
    ctx = _FakeCtx()
    plugin.register(ctx)

    import yaml

    manifest = yaml.safe_load((PLUGIN_DIR / "plugin.yaml").read_text())
    assert set(ctx.registered) == set(manifest["provides_tools"])

    for name, entry in ctx.registered.items():
        assert entry["toolset"] == "crossbot"
        assert entry["schema"]["name"] == name
        assert callable(entry["handler"])


@pytest.fixture
def plugin_env(live_crossbot_server, monkeypatch):
    monkeypatch.setenv("CROSSBOT_API_URL", f"http://127.0.0.1:{live_crossbot_server}")
    monkeypatch.setenv("CROSSBOT_API_KEY", VALID_KEY)
    return _load_plugin()


def test_send_and_pending_return_json_strings(plugin_env):
    result = plugin_env.tools.crossbot_send({"from_bot": "eddie", "to_bot": "marvin", "body": "hi"})
    assert isinstance(result, str)
    data = json.loads(result)
    assert data["status"] == "pending"

    result = plugin_env.tools.crossbot_pending({"bot_name": "marvin"})
    data = json.loads(result)
    assert len(data["messages"]) == 1
    assert data["messages"][0]["body"] == "hi"


def test_respond_cancel_status(plugin_env):
    msg_id = json.loads(
        plugin_env.tools.crossbot_send({"from_bot": "eddie", "to_bot": "marvin", "body": "hi"})
    )["id"]

    result = json.loads(plugin_env.tools.crossbot_respond({"msg_id": msg_id, "response_text": "ok"}))
    assert result["status"] == "done"

    result = json.loads(plugin_env.tools.crossbot_status({"msg_id": msg_id}))
    assert result["response_text"] == "ok"

    msg_id_2 = json.loads(
        plugin_env.tools.crossbot_send({"from_bot": "eddie", "to_bot": "marvin", "body": "hi2"})
    )["id"]
    result = json.loads(plugin_env.tools.crossbot_cancel({"msg_id": msg_id_2}))
    assert result["status"] == "cancelled"


def test_bot_registry_and_broadcast(plugin_env):
    json.loads(plugin_env.tools.crossbot_register_bot({"name": "eddie"}))
    json.loads(plugin_env.tools.crossbot_register_bot({"name": "marvin"}))

    bots = json.loads(plugin_env.tools.crossbot_list_bots({}))["bots"]
    assert {b["name"] for b in bots} == {"eddie", "marvin"}

    json.loads(plugin_env.tools.crossbot_group_add({"group": "ops", "bot": "eddie"}))
    json.loads(plugin_env.tools.crossbot_group_add({"group": "ops", "bot": "marvin"}))
    assert json.loads(plugin_env.tools.crossbot_list_groups({}))["groups"] == ["ops"]

    result = json.loads(plugin_env.tools.crossbot_broadcast({"from_bot": "eddie", "to_group": "ops", "body": "achtung"}))
    assert len(result["ids"]) == 2

    json.loads(plugin_env.tools.crossbot_group_remove({"group": "ops", "bot": "marvin"}))
    assert json.loads(plugin_env.tools.crossbot_group_members({"group": "ops"}))["members"] == ["eddie"]

    json.loads(plugin_env.tools.crossbot_revoke_bot({"name": "marvin"}))
    assert {b["name"] for b in json.loads(plugin_env.tools.crossbot_list_bots({}))["bots"]} == {"eddie"}


def test_error_returns_json_error_not_exception(plugin_env):
    """Handler-Vertrag laut Hermes-Doku: nie werfen, immer JSON zurueckgeben."""
    result = plugin_env.tools.crossbot_status({"msg_id": 999999})
    data = json.loads(result)
    assert "error" in data
