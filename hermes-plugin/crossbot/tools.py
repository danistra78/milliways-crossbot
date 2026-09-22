"""Tool handlers — der Code, der laeuft, wenn das LLM ein crossbot_*-Tool
aufruft. Regel des Hermes-Plugin-Systems: nie werfen, immer einen
JSON-String zurueckgeben (Erfolg wie Fehler)."""

import json
import os
import urllib.error
import urllib.request
from typing import Optional
from urllib.parse import quote

API_URL = os.environ.get("CROSSBOT_API_URL", "http://localhost:9191")


def _key() -> str:
    key = os.environ.get("CROSSBOT_API_KEY", "").strip()
    if not key:
        raise RuntimeError("CROSSBOT_API_KEY ist nicht gesetzt")
    return key


def _seg(value) -> str:
    """Ein Pfadsegment sicher einsetzen — Leerzeichen/Slashes wuerden die URL zerlegen."""
    return quote(str(value), safe="")


def _call(method: str, path: str, data: Optional[dict] = None) -> str:
    """Ruft die Crossbot-API auf. Gibt IMMER einen JSON-String zurueck — bei
    Fehlern {"error": "..."} statt einer Exception."""
    try:
        url = API_URL + path
        headers = {"X-API-Key": _key()}
        body = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(data).encode()
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=10) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        return json.dumps({"error": f"Crossbot-API {e.code}: {e.read().decode(errors='replace')}"})
    except Exception as e:
        return json.dumps({"error": f"Crossbot-API nicht erreichbar: {e}"})


def crossbot_send(args: dict, **kwargs) -> str:
    return _call("POST", "/msg/send", {
        "from_bot": args.get("from_bot"),
        "to_bot": args.get("to_bot"),
        "body": args.get("body"),
        "subject": args.get("subject", ""),
    })


def crossbot_broadcast(args: dict, **kwargs) -> str:
    return _call("POST", "/msg/send", {
        "from_bot": args.get("from_bot"),
        "to_group": args.get("to_group"),
        "body": args.get("body"),
        "subject": args.get("subject", ""),
    })


def crossbot_pending(args: dict, **kwargs) -> str:
    limit = args.get("limit", 100)
    return _call("GET", f"/msg/pending/{_seg(args.get('bot_name'))}?limit={_seg(limit)}")


def crossbot_respond(args: dict, **kwargs) -> str:
    return _call(
        "POST", f"/msg/respond/{_seg(args.get('msg_id'))}",
        {"response_text": args.get("response_text")},
    )


def crossbot_cancel(args: dict, **kwargs) -> str:
    return _call("DELETE", f"/msg/{_seg(args.get('msg_id'))}")


def crossbot_status(args: dict, **kwargs) -> str:
    return _call("GET", f"/msg/status/{_seg(args.get('msg_id'))}")


def crossbot_register_bot(args: dict, **kwargs) -> str:
    return _call("POST", "/bots", {"name": args.get("name")})


def crossbot_revoke_bot(args: dict, **kwargs) -> str:
    return _call("DELETE", f"/bots/{_seg(args.get('name'))}")


def crossbot_list_bots(args: dict, **kwargs) -> str:
    return _call("GET", "/bots")


def crossbot_list_groups(args: dict, **kwargs) -> str:
    return _call("GET", "/groups")


def crossbot_group_members(args: dict, **kwargs) -> str:
    return _call("GET", f"/groups/{_seg(args.get('group'))}/members")


def crossbot_group_add(args: dict, **kwargs) -> str:
    return _call("PUT", f"/groups/{_seg(args.get('group'))}/members/{_seg(args.get('bot'))}")


def crossbot_group_remove(args: dict, **kwargs) -> str:
    return _call("DELETE", f"/groups/{_seg(args.get('group'))}/members/{_seg(args.get('bot'))}")
