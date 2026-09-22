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
| `crossbot.service` | systemd-Unit (Restart=always, unprivilegiert + gehärtet) |
| `env.example` | Konfigurationsvorlage (ohne Secret) |

## Endpunkte

- `POST /msg/send` — Nachricht in die Outbox legen (from_bot, to_bot, subject, body)
- `GET /msg/pending/<bot>` — hängige Nachrichten für einen Bot abholen (FIFO)
- `POST /msg/respond/<id>` — Antwort abschliessen
- `GET /msg/status/<id>` — Status einer Nachricht
- `GET /health` — Health-Check (API-Key frei); `200 {"status":"ok"}` oder
  `503 {"status":"error"}`, Details nur im Journal

Authentifizierung via Header `X-API-Key`. Der Server startet **nicht**, wenn
`CROSSBOT_API_KEY` fehlt, noch der Platzhalter ist oder kürzer als 32 Zeichen
ist — statt stillschweigend ohne Auth zu laufen. Der Client liest das Secret
aus `.crossbot_key` neben `crossbot.py` (oder aus `$CROSSBOT_KEY_FILE`); beide
Dateien sind über `.gitignore` ausgeschlossen und gehören nie ins Repo.

## Setup

```bash
useradd --system --home /opt/crossbot --shell /usr/sbin/nologin crossbot
python3 -m venv /opt/crossbot
/opt/crossbot/bin/pip install fastapi uvicorn pydantic

cp env.example /opt/crossbot/env
openssl rand -hex 32   # Ergebnis als CROSSBOT_API_KEY in /opt/crossbot/env eintragen
chown root:crossbot /opt/crossbot/env && chmod 640 /opt/crossbot/env
chown -R crossbot:crossbot /export/hermes-shared

cp crossbot.service /etc/systemd/system/
systemctl enable --now crossbot.service
```

Auf dem Client (PVE-Host) denselben Key ablegen:

```bash
install -m 600 /dev/null .crossbot_key   # Key einfügen
```

### Datenbank

`CROSSBOT_DB_PATH` muss auf **lokalem** Speicher liegen. SQLite im WAL-Modus
braucht eine gemeinsame Shared-Memory-Datei und funktioniert über NFS/9p nicht;
`main.py` prüft nach dem Start, ob WAL wirklich aktiv ist, und schreibt sonst
eine Warnung ins Journal. Gleichzeitige Schreiber auf einem Netz-Mount riskieren
`database is locked` bis Korruption. `ReadWritePaths=` in der Unit ggf. an den
tatsächlichen Pfad anpassen.

## Status

Archiviert im September 2026 vom Container-Datenträger (LXC 101, read-only
eingehängt), nachdem der Container gestoppt war. Code anschliessend um die
Findings eines Reviews bereinigt (Auth fail-closed, Transaktions-Integrität in
`/msg/respond`, Health-Check, systemd-Härtung).

## Lizenz

MIT, siehe [LICENSE](LICENSE).
