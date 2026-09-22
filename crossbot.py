#!/usr/bin/env python3
"""Cross-Bot Tool — send/read/respond via Milliways API.

Usage:
  crossbot.py send <from> <to> "<body>" [subject]
  crossbot.py broadcast <from> <group> "<body>" [subject]
  crossbot.py pending <bot_name> [limit]
  crossbot.py respond <msg_id> "<response>"
  crossbot.py status <msg_id>
  crossbot.py cancel <msg_id>
  crossbot.py register-bot <name>          (Admin-Key noetig)
  crossbot.py revoke-bot <name>            (Admin-Key noetig)
  crossbot.py bots
  crossbot.py groups
  crossbot.py group-members <group>
  crossbot.py group-add <group> <bot>      (Admin-Key noetig)
  crossbot.py group-remove <group> <bot>   (Admin-Key noetig)
"""

import sys, os, json, urllib.request, urllib.error
from typing import NoReturn
from urllib.parse import quote

API = os.environ.get("CROSSBOT_API_URL", "http://localhost:9191")
KEY_FILE = os.environ.get("CROSSBOT_KEY_FILE", os.path.join(os.path.dirname(__file__), ".crossbot_key"))

def fail(message) -> NoReturn:
    print(message, file=sys.stderr)
    sys.exit(1)

def key():
    try:
        with open(KEY_FILE) as f:
            value = f.read().strip()
    except OSError as e:
        fail(f"API-Key nicht lesbar ({KEY_FILE}): {e}")
    if not value:
        fail(f"API-Key-Datei ist leer: {KEY_FILE}")
    return value

def seg(value):
    """Ein Pfadsegment sicher einsetzen — Leerzeichen/Slashes wuerden die URL zerlegen."""
    return quote(str(value), safe="")

def req(method, path, data=None):
    url = API + path
    headers = {"X-API-Key": key()}
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode()
    else:
        body = None
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as e:
        fail(f"Error {e.code}: {e.read().decode(errors='replace')}")
    except (urllib.error.URLError, OSError) as e:
        # Dienst gestoppt, Host nicht erreichbar, DNS/Timeout — keine Traceback-Wand.
        fail(f"Cross-Bot-API nicht erreichbar ({url}): {e}")
    try:
        return json.loads(payload)
    except ValueError as e:
        fail(f"Ungueltige Antwort von {url}: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "send" and len(sys.argv) >= 5:
        r = req("POST", "/msg/send", {
            "from_bot": sys.argv[2],
            "to_bot": sys.argv[3],
            "body": sys.argv[4],
            "subject": sys.argv[5] if len(sys.argv) > 5 else ""
        })
        print(f"#{r['id']} gesendet ({r['status']})")

    elif cmd == "pending" and len(sys.argv) >= 3:
        path = f"/msg/pending/{seg(sys.argv[2])}"
        if len(sys.argv) > 3:
            path += f"?limit={seg(sys.argv[3])}"
        r = req("GET", path)
        msgs = r.get("messages", [])
        if not msgs:
            print("Keine pending Nachrichten.")
        for m in msgs:
            print(f"  #{m['id']} von {m['from_bot']}: {m['body']}")

    elif cmd == "respond" and len(sys.argv) >= 4:
        r = req("POST", f"/msg/respond/{seg(sys.argv[2])}", {
            "response_text": sys.argv[3]
        })
        print(f"#{r['id']} beantwortet ({r['status']})")

    elif cmd == "status" and len(sys.argv) >= 3:
        r = req("GET", f"/msg/status/{seg(sys.argv[2])}")
        print(json.dumps(r, indent=2, default=str))

    elif cmd == "cancel" and len(sys.argv) >= 3:
        r = req("DELETE", f"/msg/{seg(sys.argv[2])}")
        print(f"#{r['id']} zurueckgenommen ({r['status']})")

    elif cmd == "broadcast" and len(sys.argv) >= 5:
        r = req("POST", "/msg/send", {
            "from_bot": sys.argv[2],
            "to_group": sys.argv[3],
            "body": sys.argv[4],
            "subject": sys.argv[5] if len(sys.argv) > 5 else ""
        })
        print(f"gesendet an {len(r['ids'])} Empfaenger: {r['ids']} ({r['status']})")

    elif cmd == "register-bot" and len(sys.argv) >= 3:
        r = req("POST", "/bots", {"name": sys.argv[2]})
        print(f"Bot '{r['name']}' registriert. Key (nur jetzt sichtbar):\n{r['api_key']}")

    elif cmd == "revoke-bot" and len(sys.argv) >= 3:
        r = req("DELETE", f"/bots/{seg(sys.argv[2])}")
        print(f"Bot '{r['name']}' {r['status']}")

    elif cmd == "bots":
        r = req("GET", "/bots")
        for b in r.get("bots", []):
            print(f"  {b['name']} (last_seen: {b.get('last_seen_at')})")

    elif cmd == "groups":
        r = req("GET", "/groups")
        for g in r.get("groups", []):
            print(f"  {g}")

    elif cmd == "group-members" and len(sys.argv) >= 3:
        r = req("GET", f"/groups/{seg(sys.argv[2])}/members")
        for m in r.get("members", []):
            print(f"  {m}")

    elif cmd == "group-add" and len(sys.argv) >= 4:
        r = req("PUT", f"/groups/{seg(sys.argv[2])}/members/{seg(sys.argv[3])}")
        print(f"'{r['bot']}' zu Gruppe '{r['group']}' hinzugefuegt")

    elif cmd == "group-remove" and len(sys.argv) >= 4:
        r = req("DELETE", f"/groups/{seg(sys.argv[2])}/members/{seg(sys.argv[3])}")
        print(f"'{r['bot']}' aus Gruppe '{r['group']}' entfernt")

    else:
        print(__doc__)
        sys.exit(1)
