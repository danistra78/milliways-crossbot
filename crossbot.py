#!/usr/bin/env python3
"""Cross-Bot Tool — send/read/respond via Milliways API.

Usage:
  crossbot.py send <from> <to> "<body>"
  crossbot.py pending <bot_name>
  crossbot.py respond <msg_id> "<response>"
  crossbot.py status <msg_id>
"""

import sys, os, json, urllib.request, urllib.error

API = "http://192.168.0.10:9191"
KEY_FILE = os.path.join(os.path.dirname(__file__), ".crossbot_key")

def key():
    with open(KEY_FILE) as f:
        return f.read().strip()

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
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"Error {e.code}: {e.read().decode()}", file=sys.stderr)
        sys.exit(1)

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
        r = req("GET", f"/msg/pending/{sys.argv[2]}")
        msgs = r.get("messages", [])
        if not msgs:
            print("Keine pending Nachrichten.")
        for m in msgs:
            print(f"  #{m['id']} von {m['from_bot']}: {m['body']}")

    elif cmd == "respond" and len(sys.argv) >= 4:
        r = req("POST", f"/msg/respond/{sys.argv[2]}", {
            "response_text": sys.argv[3]
        })
        print(f"#{r['id']} beantwortet ({r['status']})")

    elif cmd == "status" and len(sys.argv) >= 3:
        r = req("GET", f"/msg/status/{sys.argv[2]}")
        print(json.dumps(r, indent=2, default=str))

    else:
        print("Usage:")
        print("  send <from> <to> <body> [subject]")
        print("  pending <bot_name>")
        print("  respond <msg_id> <response>")
        print("  status <msg_id>")
        sys.exit(1)
