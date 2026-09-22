# milliways-crossbot

Cross-Bot Message Bus API — HTTP-Queue für die Kommunikation zwischen
beliebig vielen Bots/Agents, inkl. Bot-Registry und Gruppen/Broadcast.

Läuft als systemd-Dienst, standardmässig auf Port 9191.

## Komponenten

| Datei | Zweck |
|---|---|
| `main.py` | FastAPI-Server (SQLite-Queue, API-Key-Auth) |
| `crossbot.py` | Client-Helfer für Aufrufe vom Client-Host |
| `crossbot.service` | systemd-Unit (Restart=always, unprivilegiert + gehärtet) |
| `env.example` | Konfigurationsvorlage (ohne Secret) |
| `requirements.txt` | Laufzeit-Abhängigkeiten |
| `requirements-dev.txt` | zusätzlich Test-Abhängigkeiten (pytest, httpx) |
| `tests/` | pytest-Testsuite |

## Endpunkte

**Nachrichten**
- `POST /msg/send` — Nachricht senden. `to_bot` ODER `to_group` (genau eins),
  `from_bot`, `subject`, `body`. Bei `to_group` Antwort `{"ids": [...]}`,
  sonst `{"id": ...}`
- `GET /msg/pending/<bot>?limit=<n>` — hängige Nachrichten für einen Bot abholen
  (FIFO, `limit` optional, Standard 100, max. 1000)
- `POST /msg/respond/<id>` — Antwort abschliessen (nur der Empfänger darf)
- `DELETE /msg/<id>` — noch offene (pending) Nachricht zurücknehmen (nur der Absender darf)
- `GET /msg/status/<id>` — Status einer Nachricht (nur Absender/Empfänger dürfen)
- `GET /health` — Health-Check (API-Key frei); `200 {"status":"ok"}` oder
  `503 {"status":"error"}`, Details nur im Journal

**Bot-Registry** (nur Admin-Key darf registrieren/entfernen)
- `POST /bots` — Bot registrieren, `{"name": ...}` → gibt den Bot-Key **einmalig** zurück
- `GET /bots` — registrierte Bots auflisten (inkl. `last_seen_at`)
- `DELETE /bots/<name>` — Bot-Key widerrufen

**Gruppen** (Mitgliederverwaltung nur Admin-Key, Lesen für alle authentifizierten Bots)
- `GET /groups`, `GET /groups/<name>/members`
- `PUT /groups/<name>/members/<bot>`, `DELETE /groups/<name>/members/<bot>`
- Broadcast = Senden mit `to_group` statt `to_bot`

Authentifizierung via Header `X-API-Key`. Zwei Arten von Keys:

- **Admin-Key** (`CROSSBOT_API_KEY`): darf alles, inkl. Bot-/Gruppenverwaltung.
  Der Server startet **nicht**, wenn er fehlt, noch der Platzhalter ist oder
  kürzer als 32 Zeichen ist — statt stillschweigend ohne Auth zu laufen.
- **Bot-Key**: über `POST /bots` ausgestellt, in der DB nur als SHA-256-Hash
  gespeichert. Ein Bot darf mit seinem Key nur als er selbst senden, sein
  eigenes Postfach lesen und nur eigene/an ihn gerichtete Nachrichten
  beantworten, zurücknehmen oder deren Status abfragen.

Der Client liest sein Secret aus `.crossbot_key` neben `crossbot.py` (oder aus
`$CROSSBOT_KEY_FILE`); beide Dateien sind über `.gitignore` ausgeschlossen und
gehören nie ins Repo.

## Setup

```bash
useradd --system --home /opt/crossbot --shell /usr/sbin/nologin crossbot
python3 -m venv /opt/crossbot
/opt/crossbot/bin/pip install -r requirements.txt

cp env.example /opt/crossbot/env
openssl rand -hex 32   # Ergebnis als CROSSBOT_API_KEY in /opt/crossbot/env eintragen
chown root:crossbot /opt/crossbot/env && chmod 640 /opt/crossbot/env
chown -R crossbot:crossbot /pfad/zur/datenbank

cp crossbot.service /etc/systemd/system/
systemctl enable --now crossbot.service
```

Auf dem Client den Admin-Key ablegen:

```bash
install -m 600 /dev/null .crossbot_key   # Key einfügen
```

### Bots & Gruppen anlegen

```bash
./crossbot.py register-bot eddie     # Key ausgeben, in eddies .crossbot_key legen
./crossbot.py register-bot marvin
./crossbot.py group-add ops eddie
./crossbot.py group-add ops marvin

./crossbot.py send eddie marvin "hallo"
./crossbot.py broadcast eddie ops "an alle"
```

### Datenbank

`CROSSBOT_DB_PATH` muss auf **lokalem** Speicher liegen. SQLite im WAL-Modus
braucht eine gemeinsame Shared-Memory-Datei und funktioniert über NFS/9p nicht;
`main.py` prüft nach dem Start, ob WAL wirklich aktiv ist, und schreibt sonst
eine Warnung ins Journal. Gleichzeitige Schreiber auf einem Netz-Mount riskieren
`database is locked` bis Korruption. `ReadWritePaths=` in der Unit ggf. an den
tatsächlichen Pfad anpassen.

### Aufräumen

Abgeschlossene Nachrichten (`done`/`cancelled`) werden automatisch entfernt,
sobald sie älter als `CROSSBOT_RETENTION_DAYS` (Standard 30 Tage) sind —
Prüfung beim Start und danach alle `CROSSBOT_CLEANUP_INTERVAL_SECONDS`
(Standard 3600s). `CROSSBOT_RETENTION_DAYS<=0` deaktiviert das Aufräumen.

## Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

Läuft auch automatisch per GitHub Actions bei jedem Push/PR
(`.github/workflows/ci.yml`).

## Status

Archiviert im September 2026 vom ursprünglichen Container-Datenträger, nachdem
dieser gestoppt war. Code anschliessend um die Findings eines Reviews bereinigt
(Auth fail-closed, Transaktions-Integrität in `/msg/respond`, Health-Check,
systemd-Härtung).

## Lizenz

MIT, siehe [LICENSE](LICENSE).
