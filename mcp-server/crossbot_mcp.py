#!/usr/bin/env python3
"""MCP-Server fuer den Cross-Bot Message Bus — macht die HTTP-API als Tools
fuer Claude Code (oder jeden anderen MCP-Client) verfuegbar."""

import json
import os
import urllib.error
import urllib.request
from typing import Optional
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP

API_URL = os.environ.get("CROSSBOT_API_URL", "http://localhost:9191")
KEY_FILE = os.environ.get(
    "CROSSBOT_KEY_FILE", os.path.join(os.path.dirname(__file__), "..", ".crossbot_key")
)


def _load_key() -> str:
    """Liest den API-Key aus CROSSBOT_API_KEY oder, falls nicht gesetzt, aus
    CROSSBOT_KEY_FILE (gleiche Konvention wie crossbot.py)."""
    env_key = os.environ.get("CROSSBOT_API_KEY")
    if env_key:
        return env_key
    try:
        with open(KEY_FILE) as f:
            value = f.read().strip()
    except OSError as e:
        raise RuntimeError(f"API-Key nicht lesbar ({KEY_FILE}): {e}") from e
    if not value:
        raise RuntimeError(f"API-Key-Datei ist leer: {KEY_FILE}")
    return value


def _seg(value) -> str:
    """Ein Pfadsegment sicher einsetzen — Leerzeichen/Slashes wuerden die URL zerlegen."""
    return quote(str(value), safe="")


def _request(method: str, path: str, data: Optional[dict] = None) -> dict:
    """Ruft die Crossbot-API auf und wirft bei Fehlern eine normale Exception,
    statt den Prozess zu beenden — ein einzelner fehlgeschlagener Tool-Call
    darf den MCP-Server nicht abschiessen."""
    url = API_URL + path
    headers = {"X-API-Key": _load_key()}
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode()
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Crossbot-API {e.code}: {e.read().decode(errors='replace')}") from e
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(f"Crossbot-API nicht erreichbar ({url}): {e}") from e
    try:
        return json.loads(payload)
    except ValueError as e:
        raise RuntimeError(f"Ungueltige Antwort von {url}: {e}") from e


mcp = FastMCP("crossbot")


@mcp.tool()
def crossbot_send(from_bot: str, to_bot: str, body: str, subject: str = "") -> dict:
    """Sendet eine Nachricht an einen einzelnen Bot."""
    return _request(
        "POST", "/msg/send",
        {"from_bot": from_bot, "to_bot": to_bot, "body": body, "subject": subject},
    )


@mcp.tool()
def crossbot_broadcast(from_bot: str, to_group: str, body: str, subject: str = "") -> dict:
    """Sendet eine Nachricht an alle Mitglieder einer Gruppe (Broadcast)."""
    return _request(
        "POST", "/msg/send",
        {"from_bot": from_bot, "to_group": to_group, "body": body, "subject": subject},
    )


@mcp.tool()
def crossbot_pending(bot_name: str, limit: int = 100) -> dict:
    """Holt die haengigen (pending) Nachrichten fuer einen Bot, FIFO."""
    return _request("GET", f"/msg/pending/{_seg(bot_name)}?limit={_seg(limit)}")


@mcp.tool()
def crossbot_respond(msg_id: int, response_text: str) -> dict:
    """Beantwortet eine Nachricht und schliesst sie ab."""
    return _request("POST", f"/msg/respond/{_seg(msg_id)}", {"response_text": response_text})


@mcp.tool()
def crossbot_cancel(msg_id: int) -> dict:
    """Nimmt eine noch offene (pending) Nachricht zurueck."""
    return _request("DELETE", f"/msg/{_seg(msg_id)}")


@mcp.tool()
def crossbot_status(msg_id: int) -> dict:
    """Fragt den Status einer Nachricht ab."""
    return _request("GET", f"/msg/status/{_seg(msg_id)}")


@mcp.tool()
def crossbot_register_bot(name: str) -> dict:
    """Registriert einen neuen Bot (Admin-Key noetig). Gibt den Bot-Key EINMALIG zurueck."""
    return _request("POST", "/bots", {"name": name})


@mcp.tool()
def crossbot_revoke_bot(name: str) -> dict:
    """Widerruft den Key eines Bots (Admin-Key noetig)."""
    return _request("DELETE", f"/bots/{_seg(name)}")


@mcp.tool()
def crossbot_list_bots() -> dict:
    """Listet alle registrierten Bots (inkl. last_seen_at)."""
    return _request("GET", "/bots")


@mcp.tool()
def crossbot_list_groups() -> dict:
    """Listet alle existierenden Gruppen."""
    return _request("GET", "/groups")


@mcp.tool()
def crossbot_group_members(group: str) -> dict:
    """Listet die Mitglieder einer Gruppe."""
    return _request("GET", f"/groups/{_seg(group)}/members")


@mcp.tool()
def crossbot_group_add(group: str, bot: str) -> dict:
    """Fuegt einen Bot einer Gruppe hinzu (Admin-Key noetig)."""
    return _request("PUT", f"/groups/{_seg(group)}/members/{_seg(bot)}")


@mcp.tool()
def crossbot_group_remove(group: str, bot: str) -> dict:
    """Entfernt einen Bot aus einer Gruppe (Admin-Key noetig)."""
    return _request("DELETE", f"/groups/{_seg(group)}/members/{_seg(bot)}")


if __name__ == "__main__":
    mcp.run()
