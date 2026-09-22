# crossbot MCP-Server

Macht die [Cross-Bot Message Bus API](../README.md) als MCP-Tools verfügbar,
damit Claude (Code/Desktop, oder jeder andere MCP-Client) direkt senden,
abholen, beantworten kann — ohne rohe `curl`-Aufrufe.

## Tools

| Tool | Entspricht |
|---|---|
| `crossbot_send` | `POST /msg/send` (an einen Bot) |
| `crossbot_broadcast` | `POST /msg/send` (an eine Gruppe) |
| `crossbot_pending` | `GET /msg/pending/<bot>` |
| `crossbot_respond` | `POST /msg/respond/<id>` |
| `crossbot_cancel` | `DELETE /msg/<id>` |
| `crossbot_status` | `GET /msg/status/<id>` |
| `crossbot_register_bot` | `POST /bots` (Admin-Key) |
| `crossbot_revoke_bot` | `DELETE /bots/<name>` (Admin-Key) |
| `crossbot_list_bots` | `GET /bots` |
| `crossbot_list_groups` | `GET /groups` |
| `crossbot_group_members` | `GET /groups/<name>/members` |
| `crossbot_group_add` | `PUT /groups/<name>/members/<bot>` (Admin-Key) |
| `crossbot_group_remove` | `DELETE /groups/<name>/members/<bot>` (Admin-Key) |

Scope-Regeln (wer darf was) sind identisch zur HTTP-API — siehe
[../README.md](../README.md#endpunkte). Ein Fehler (403/404/Verbindung weg)
wird als normale Tool-Fehlermeldung zurückgegeben, nicht als Absturz des
Servers.

## Konfiguration

| Variable | Zweck | Default |
|---|---|---|
| `CROSSBOT_API_URL` | Basis-URL der Crossbot-API | `http://localhost:9191` |
| `CROSSBOT_API_KEY` | Key direkt als Env-Var | — |
| `CROSSBOT_KEY_FILE` | Alternativ: Key aus Datei lesen | `../.crossbot_key` |

Genau ein Key (Admin- oder Bot-Key, siehe Haupt-README) — je nachdem, als
welche Identität dieser MCP-Server auftreten soll.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## In Claude Code registrieren

```bash
claude mcp add crossbot \
  --env CROSSBOT_API_URL=http://localhost:9191 \
  --env CROSSBOT_API_KEY=<dein-key> \
  -- python3 /pfad/zu/mcp-server/crossbot_mcp.py
```

Danach stehen die `crossbot_*`-Tools in der Session zur Verfügung.
