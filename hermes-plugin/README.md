# crossbot Hermes-Plugin

Natives [Hermes Agent](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins)-Plugin
für den [Cross-Bot Message Bus](../README.md). Registriert 13 `crossbot_*`-Tools
(Nachrichten, Bot-Registry, Gruppen/Broadcast) direkt in Hermes — kein MCP nötig.

**Ungetestet gegen die echte Hermes-Runtime** — hier gibt es kein `hermes`
zum Installieren/Validieren. Getestet ist nur, dass `register(ctx)` alle in
`plugin.yaml` deklarierten Tools mit passendem Schema verdrahtet und dass die
Handler tatsächlich gegen die Crossbot-API funktionieren (`tests/test_hermes_plugin.py`).
Vor dem produktiven Einsatz mit `hermes plugins doctor . --ci` validieren.

## Installation

```bash
mkdir -p ~/.hermes/plugins/crossbot
cp -r hermes-plugin/crossbot/* ~/.hermes/plugins/crossbot/

hermes plugins doctor ~/.hermes/plugins/crossbot --ci
hermes plugins enable crossbot
```

## Konfiguration

`plugin.yaml` deklariert `CROSSBOT_API_KEY` als `requires_env` (secret) —
Hermes fragt es beim Install interaktiv ab und legt es in `.env` ab.
Optional zusätzlich in `.env` oder der Umgebung:

```bash
CROSSBOT_API_URL=http://localhost:9191   # Default, falls nicht gesetzt
```

Scope-Regeln (wer darf was) sind identisch zur HTTP-API — siehe
[../README.md](../README.md#endpunkte).

## Struktur

```
crossbot/
├── plugin.yaml   # Manifest: Name, provides_tools, requires_env
├── __init__.py   # register(ctx): verdrahtet Schemas -> Handler
├── schemas.py     # Was das LLM sieht (Tool-Beschreibungen + Parameter)
└── tools.py       # Handler — geben laut Hermes-Konvention IMMER einen
                    # JSON-String zurück, werfen nie
```
