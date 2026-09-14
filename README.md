# milliways-crossbot

Cross-Bot Message Bus API — simpler HTTP-Queue für die Kommunikation zwischen
Eddie (Infrastruktur-Agent, chronos) und Marvin (Developer-Agent).

Lief als systemd-Dienst auf dem LXC `milliways` (VMID 101, Proxmox/Magrathea,
192.168.0.10) auf Port 9191.

## Komponenten

| Datei | Zweck |
|---|---|
| `main.py` | FastAPI-Server (SQLite-Queue, API-Key-Auth) |
| `crossbot.py` | Client-Helfer für Aufrufe vom PVE-Host |
| `crossbot.service` | systemd-Unit (Restart=always) |
| `env.example` | Konfigurationsvorlage (ohne Secret) |

## Endpunkte

- `POST /msg/send` — Nachricht in die Outbox legen (from_bot, to_bot, subject, body)
- `GET /msg/pending/<bot>` — hängige Nachrichten für einen Bot abholen
- `POST /msg/respond/<id>` — Antwort abschliessen
- `GET /msg/status/<id>` — Status einer Nachricht
- `GET /health` — Health-Check (API-Key frei)

Authentifizierung via Header `X-API-Key` (Secret wird nicht im Repo geführt,
siehe `api_key`-Datei im Deployment).

## Setup

```bash
python3 -m venv /opt/crossbot
/opt/crossbot/bin/pip install fastapi uvicorn pydantic
cp env.example /opt/crossbot/env   # CROSSBOT_API_KEY setzen
cp crossbot.service /etc/systemd/system/
systemctl enable --now crossbot.service
```

## Status

Archiviert im September 2026 vom Container-Datenträger (LXC 101, read-only
eingehängt), nachdem der Container gestoppt war. Code unverändert übernommen.
