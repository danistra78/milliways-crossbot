#!/usr/bin/env python3
"""Cross-Bot Message Bus API — fuer Eddie & Marvin."""

import hmac
import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

DB_PATH = os.environ.get("CROSSBOT_DB_PATH", "/export/hermes-shared/multi_agent_tg_shared.db")
API_KEY = os.environ.get("CROSSBOT_API_KEY", "")
HOST = os.environ.get("CROSSBOT_HOST", "0.0.0.0")
PORT = int(os.environ.get("CROSSBOT_PORT", "9191"))
# Wartezeit auf eine belegte Schreibsperre, bevor SQLite "database is locked" meldet.
BUSY_TIMEOUT = float(os.environ.get("CROSSBOT_BUSY_TIMEOUT", "5.0"))

MIN_API_KEY_LENGTH = 32
PLACEHOLDER_API_KEYS = {"***", "change-me", "changeme", "secret", "geheim"}

logger = logging.getLogger("crossbot")

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, from_bot TEXT,
        to_bot TEXT, subject TEXT, body TEXT, status TEXT DEFAULT 'pending',
        kanban_task_id INTEGER, response_text TEXT, completed_at INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS response_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER,
        outbox_id INTEGER, bot_name TEXT, response TEXT
    )""",
)


class SendRequest(BaseModel):
    from_bot: str
    to_bot: str
    subject: str = ""
    body: str


class RespondRequest(BaseModel):
    response_text: str


def connect() -> sqlite3.Connection:
    """Verbindung fuer einen einzelnen Request — ohne Schema-Arbeit."""
    conn = sqlite3.connect(DB_PATH, timeout=BUSY_TIMEOUT)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema() -> None:
    """Journal-Modus und Tabellen einmalig beim Start einrichten."""
    conn = connect()
    try:
        # PRAGMA journal_mode meldet den *aktiven* Modus, auch wenn das Setzen
        # scheitert — deshalb pruefen statt blind vertrauen. WAL braucht eine
        # gemeinsame Shared-Memory-Datei und funktioniert auf NFS/9p nicht.
        mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        if str(mode).lower() != "wal":
            logger.warning(
                "journal_mode=WAL konnte nicht aktiviert werden (aktiv: %s). Liegt %s "
                "auf einem Netz-Mount (NFS/9p)? Gleichzeitige Schreiber riskieren dort "
                "'database is locked' oder Korruption — Datenbank auf lokalen Speicher legen.",
                mode,
                DB_PATH,
            )
        for statement in SCHEMA:
            conn.execute(statement)
        conn.commit()
    finally:
        conn.close()


def api_key_problem(key: str) -> Optional[str]:
    """Beschreibt, warum der konfigurierte API-Key unbrauchbar ist — sonst None."""
    if not key:
        return "CROSSBOT_API_KEY ist nicht gesetzt"
    if key in PLACEHOLDER_API_KEYS:
        return "CROSSBOT_API_KEY ist noch der Platzhalter aus env.example"
    if len(key) < MIN_API_KEY_LENGTH:
        return f"CROSSBOT_API_KEY ist kuerzer als {MIN_API_KEY_LENGTH} Zeichen"
    return None


def verify_key(x_api_key: Optional[str]) -> None:
    # Fail closed: ohne brauchbaren Server-Key wird nichts bedient, statt die
    # Authentifizierung stillschweigend zu ueberspringen.
    if api_key_problem(API_KEY) is not None:
        raise HTTPException(status_code=503, detail="API key not configured on server")
    if not x_api_key or not hmac.compare_digest(
        x_api_key.encode("utf-8"), API_KEY.encode("utf-8")
    ):
        raise HTTPException(status_code=403, detail="Invalid API Key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    problem = api_key_problem(API_KEY)
    if problem is not None:
        raise RuntimeError(f"Start abgebrochen: {problem}")
    init_schema()
    yield

app = FastAPI(title="Cross-Bot Message Bus", version="1.0", lifespan=lifespan)


@app.post("/msg/send")
def send_msg(req: SendRequest, x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    conn = connect()
    try:
        now = int(time.time())
        with conn:
            cur = conn.execute(
                "INSERT INTO outbox (ts, from_bot, to_bot, subject, body, status) VALUES (?, ?, ?, ?, ?, 'pending')",
                (now, req.from_bot, req.to_bot, req.subject, req.body),
            )
        return {"id": cur.lastrowid, "status": "pending"}
    finally:
        conn.close()


@app.get("/msg/pending/{bot_name}")
def get_pending(bot_name: str, x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    conn = connect()
    try:
        rows = conn.execute(
            # id als Tiebreaker: ts hat nur Sekundenaufloesung, sonst ist die
            # Reihenfolge zweier Nachrichten aus derselben Sekunde beliebig.
            "SELECT id, ts, from_bot, to_bot, subject, body, status FROM outbox "
            "WHERE to_bot=? AND status='pending' ORDER BY ts ASC, id ASC",
            (bot_name,),
        ).fetchall()
        return {"messages": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.post("/msg/respond/{msg_id}")
def respond(msg_id: int, req: RespondRequest, x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    conn = connect()
    try:
        now = int(time.time())
        # Status-Update und response_log in *einer* Transaktion: sonst bleibt bei
        # einem Fehler im Insert die Nachricht 'done' zurueck, waehrend der
        # Aufrufer einen Fehler sieht und beim Retry 404 bekommt.
        with conn:
            cur = conn.execute(
                "UPDATE outbox SET status='done', response_text=?, completed_at=? WHERE id=? AND status='pending'",
                (req.response_text, now, msg_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Not found or already answered")
            msg = conn.execute(
                "SELECT from_bot, to_bot FROM outbox WHERE id=?", (msg_id,)
            ).fetchone()
            conn.execute(
                "INSERT INTO response_log (ts, outbox_id, bot_name, response) VALUES (?, ?, ?, ?)",
                (now, msg_id, msg["to_bot"], req.response_text),
            )
        return {"id": msg_id, "status": "done"}
    finally:
        conn.close()


@app.get("/msg/status/{msg_id}")
def get_status(msg_id: int, x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM outbox WHERE id=?", (msg_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        return dict(row)
    finally:
        conn.close()


@app.get("/health")
def health():
    # Der Verbindungsaufbau selbst ist der Teil, der ausfaellt (Mount weg,
    # Datei nicht lesbar) — er muss deshalb *innerhalb* des try stehen.
    try:
        conn = connect()
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()
    except Exception:
        # Details nur ins Log: /health ist absichtlich ohne API-Key erreichbar
        # und soll keine internen Pfade preisgeben.
        logger.exception("Health-Check fehlgeschlagen")
        return JSONResponse(status_code=503, content={"status": "error"})
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    uvicorn.run(app, host=HOST, port=PORT)
