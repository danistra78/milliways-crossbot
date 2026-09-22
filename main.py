#!/usr/bin/env python3
"""Cross-Bot Message Bus API — fuer mehrere Bots/Agents."""

import asyncio
import hashlib
import hmac
import logging
import os
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

DB_PATH = os.environ.get("CROSSBOT_DB_PATH", "/export/hermes-shared/multi_agent_tg_shared.db")
API_KEY = os.environ.get("CROSSBOT_API_KEY", "")
HOST = os.environ.get("CROSSBOT_HOST", "0.0.0.0")
PORT = int(os.environ.get("CROSSBOT_PORT", "9191"))
# Wartezeit auf eine belegte Schreibsperre, bevor SQLite "database is locked" meldet.
BUSY_TIMEOUT = float(os.environ.get("CROSSBOT_BUSY_TIMEOUT", "5.0"))
# Wie lange abgeschlossene (done/cancelled) Nachrichten aufbewahrt werden, bevor
# sie aufgeraeumt werden. <= 0 deaktiviert das Aufraeumen.
RETENTION_DAYS = float(os.environ.get("CROSSBOT_RETENTION_DAYS", "30"))
CLEANUP_INTERVAL = float(os.environ.get("CROSSBOT_CLEANUP_INTERVAL_SECONDS", "3600"))

MIN_API_KEY_LENGTH = 32
PLACEHOLDER_API_KEYS = {"***", "change-me", "changeme", "secret", "geheim"}

# Sentinel-Identitaet fuer den globalen CROSSBOT_API_KEY: darf alles, inkl.
# Bot-Verwaltung. Einzelne Bots authentifizieren sich stattdessen mit einem
# eigenen, ueber /bots ausgestellten Key und sind auf ihre eigene Identitaet
# beschraenkt (siehe scope-Pruefungen je Endpunkt).
ADMIN = "__admin__"

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
    """CREATE TABLE IF NOT EXISTS bots (
        name TEXT PRIMARY KEY, api_key_hash TEXT NOT NULL,
        created_at INTEGER, last_seen_at INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS group_members (
        group_name TEXT NOT NULL, bot_name TEXT NOT NULL,
        PRIMARY KEY (group_name, bot_name)
    )""",
)


class SendRequest(BaseModel):
    from_bot: str
    to_bot: Optional[str] = None
    to_group: Optional[str] = None
    subject: str = ""
    body: str


class RespondRequest(BaseModel):
    response_text: str


class RegisterBotRequest(BaseModel):
    name: str


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


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def lookup_bot(key: str) -> Optional[str]:
    """Findet den Bot-Namen zu einem Bot-eigenen Key und aktualisiert last_seen_at."""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT name FROM bots WHERE api_key_hash=?", (hash_key(key),)
        ).fetchone()
        if row is None:
            return None
        with conn:
            conn.execute(
                "UPDATE bots SET last_seen_at=? WHERE name=?", (int(time.time()), row["name"])
            )
        return row["name"]
    finally:
        conn.close()


def caller_identity(x_api_key: Optional[str] = Header(None)) -> str:
    """Authentifiziert den Request und liefert die Anrufer-Identitaet:
    ADMIN fuer den globalen CROSSBOT_API_KEY, sonst der Bot-Name."""
    # Fail closed: ohne brauchbaren Server-Key wird nichts bedient, statt die
    # Authentifizierung stillschweigend zu ueberspringen.
    if api_key_problem(API_KEY) is not None:
        raise HTTPException(status_code=503, detail="API key not configured on server")
    if x_api_key and hmac.compare_digest(x_api_key.encode("utf-8"), API_KEY.encode("utf-8")):
        return ADMIN
    bot = lookup_bot(x_api_key) if x_api_key else None
    if bot is None:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return bot


def require_admin(caller: str) -> None:
    if caller != ADMIN:
        raise HTTPException(status_code=403, detail="Admin key required")


def cleanup_old_messages() -> int:
    """Loescht abgeschlossene Nachrichten (done/cancelled) aelter als RETENTION_DAYS.

    Gibt die Anzahl geloeschter outbox-Zeilen zurueck. RETENTION_DAYS <= 0
    deaktiviert das Aufraeumen.
    """
    if RETENTION_DAYS <= 0:
        return 0
    cutoff = int(time.time() - RETENTION_DAYS * 86400)
    conn = connect()
    try:
        with conn:
            conn.execute(
                "DELETE FROM response_log WHERE outbox_id IN ("
                "SELECT id FROM outbox WHERE status IN ('done', 'cancelled') "
                "AND completed_at IS NOT NULL AND completed_at < ?)",
                (cutoff,),
            )
            cur = conn.execute(
                "DELETE FROM outbox WHERE status IN ('done', 'cancelled') "
                "AND completed_at IS NOT NULL AND completed_at < ?",
                (cutoff,),
            )
            return cur.rowcount
    finally:
        conn.close()


async def cleanup_loop() -> None:
    """Raeumt periodisch alte Nachrichten weg, bis der Task abgebrochen wird."""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        try:
            deleted = cleanup_old_messages()
            if deleted:
                logger.info("Aufraeumen: %d abgeschlossene Nachricht(en) entfernt", deleted)
        except Exception:
            logger.exception("Aufraeumen fehlgeschlagen")


@asynccontextmanager
async def lifespan(app: FastAPI):
    problem = api_key_problem(API_KEY)
    if problem is not None:
        raise RuntimeError(f"Start abgebrochen: {problem}")
    init_schema()
    cleanup_old_messages()
    task = asyncio.create_task(cleanup_loop()) if CLEANUP_INTERVAL > 0 and RETENTION_DAYS > 0 else None
    try:
        yield
    finally:
        if task is not None:
            task.cancel()

app = FastAPI(title="Cross-Bot Message Bus", version="1.0", lifespan=lifespan)


@app.post("/msg/send")
def send_msg(req: SendRequest, caller: str = Depends(caller_identity)):
    if caller != ADMIN and caller != req.from_bot:
        raise HTTPException(status_code=403, detail="from_bot must match the authenticated bot")
    if bool(req.to_bot) == bool(req.to_group):
        raise HTTPException(status_code=400, detail="Exactly one of to_bot or to_group required")
    conn = connect()
    try:
        now = int(time.time())
        if req.to_group:
            recipients = [
                r["bot_name"]
                for r in conn.execute(
                    "SELECT bot_name FROM group_members WHERE group_name=? ORDER BY bot_name",
                    (req.to_group,),
                ).fetchall()
            ]
            if not recipients:
                raise HTTPException(status_code=404, detail="Group not found or empty")
        else:
            recipients = [req.to_bot]
        ids: List[int] = []
        with conn:
            for to_bot in recipients:
                cur = conn.execute(
                    "INSERT INTO outbox (ts, from_bot, to_bot, subject, body, status) VALUES (?, ?, ?, ?, ?, 'pending')",
                    (now, req.from_bot, to_bot, req.subject, req.body),
                )
                ids.append(cur.lastrowid)
        if req.to_group:
            return {"ids": ids, "status": "pending"}
        return {"id": ids[0], "status": "pending"}
    finally:
        conn.close()


@app.get("/msg/pending/{bot_name}")
def get_pending(
    bot_name: str,
    caller: str = Depends(caller_identity),
    limit: int = Query(100, ge=1, le=1000),
):
    if caller != ADMIN and caller != bot_name:
        raise HTTPException(status_code=403, detail="Can only fetch your own inbox")
    conn = connect()
    try:
        rows = conn.execute(
            # id als Tiebreaker: ts hat nur Sekundenaufloesung, sonst ist die
            # Reihenfolge zweier Nachrichten aus derselben Sekunde beliebig.
            "SELECT id, ts, from_bot, to_bot, subject, body, status FROM outbox "
            "WHERE to_bot=? AND status='pending' ORDER BY ts ASC, id ASC LIMIT ?",
            (bot_name, limit),
        ).fetchall()
        return {"messages": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.delete("/msg/{msg_id}")
def cancel(msg_id: int, caller: str = Depends(caller_identity)):
    """Nimmt eine noch nicht abgeholte/beantwortete Nachricht zurueck."""
    conn = connect()
    try:
        now = int(time.time())
        with conn:
            msg = conn.execute(
                "SELECT from_bot FROM outbox WHERE id=? AND status='pending'", (msg_id,)
            ).fetchone()
            if msg is None:
                raise HTTPException(status_code=404, detail="Not found or already answered")
            if caller != ADMIN and caller != msg["from_bot"]:
                raise HTTPException(status_code=403, detail="Only the sender can cancel")
            cur = conn.execute(
                "UPDATE outbox SET status='cancelled', completed_at=? WHERE id=? AND status='pending'",
                (now, msg_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Not found or already answered")
        return {"id": msg_id, "status": "cancelled"}
    finally:
        conn.close()


@app.post("/msg/respond/{msg_id}")
def respond(msg_id: int, req: RespondRequest, caller: str = Depends(caller_identity)):
    conn = connect()
    try:
        now = int(time.time())
        # Status-Update und response_log in *einer* Transaktion: sonst bleibt bei
        # einem Fehler im Insert die Nachricht 'done' zurueck, waehrend der
        # Aufrufer einen Fehler sieht und beim Retry 404 bekommt.
        with conn:
            msg = conn.execute(
                "SELECT to_bot FROM outbox WHERE id=? AND status='pending'", (msg_id,)
            ).fetchone()
            if msg is None:
                raise HTTPException(status_code=404, detail="Not found or already answered")
            if caller != ADMIN and caller != msg["to_bot"]:
                raise HTTPException(status_code=403, detail="Only the recipient can respond")
            cur = conn.execute(
                "UPDATE outbox SET status='done', response_text=?, completed_at=? WHERE id=? AND status='pending'",
                (req.response_text, now, msg_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Not found or already answered")
            conn.execute(
                "INSERT INTO response_log (ts, outbox_id, bot_name, response) VALUES (?, ?, ?, ?)",
                (now, msg_id, msg["to_bot"], req.response_text),
            )
        return {"id": msg_id, "status": "done"}
    finally:
        conn.close()


@app.get("/msg/status/{msg_id}")
def get_status(msg_id: int, caller: str = Depends(caller_identity)):
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM outbox WHERE id=?", (msg_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        if caller != ADMIN and caller not in (row["from_bot"], row["to_bot"]):
            raise HTTPException(status_code=403, detail="Not authorized for this message")
        return dict(row)
    finally:
        conn.close()


@app.post("/bots")
def register_bot(req: RegisterBotRequest, caller: str = Depends(caller_identity)):
    """Registriert einen neuen Bot und gibt seinen Key zurueck (nur dieses eine Mal)."""
    require_admin(caller)
    if not req.name or req.name == ADMIN:
        raise HTTPException(status_code=400, detail="Invalid bot name")
    new_key = secrets.token_hex(32)
    conn = connect()
    try:
        try:
            with conn:
                conn.execute(
                    "INSERT INTO bots (name, api_key_hash, created_at) VALUES (?, ?, ?)",
                    (req.name, hash_key(new_key), int(time.time())),
                )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Bot already registered")
        return {"name": req.name, "api_key": new_key}
    finally:
        conn.close()


@app.get("/bots")
def list_bots(caller: str = Depends(caller_identity)):
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT name, created_at, last_seen_at FROM bots ORDER BY name"
        ).fetchall()
        return {"bots": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.delete("/bots/{name}")
def revoke_bot(name: str, caller: str = Depends(caller_identity)):
    require_admin(caller)
    conn = connect()
    try:
        with conn:
            cur = conn.execute("DELETE FROM bots WHERE name=?", (name,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Bot not found")
            conn.execute("DELETE FROM group_members WHERE bot_name=?", (name,))
        return {"name": name, "status": "revoked"}
    finally:
        conn.close()


@app.get("/groups")
def list_groups(caller: str = Depends(caller_identity)):
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT DISTINCT group_name FROM group_members ORDER BY group_name"
        ).fetchall()
        return {"groups": [r["group_name"] for r in rows]}
    finally:
        conn.close()


@app.get("/groups/{group_name}/members")
def list_group_members(group_name: str, caller: str = Depends(caller_identity)):
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT bot_name FROM group_members WHERE group_name=? ORDER BY bot_name",
            (group_name,),
        ).fetchall()
        return {"group": group_name, "members": [r["bot_name"] for r in rows]}
    finally:
        conn.close()


@app.put("/groups/{group_name}/members/{bot_name}")
def add_group_member(group_name: str, bot_name: str, caller: str = Depends(caller_identity)):
    require_admin(caller)
    conn = connect()
    try:
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO group_members (group_name, bot_name) VALUES (?, ?)",
                (group_name, bot_name),
            )
        return {"group": group_name, "bot": bot_name, "status": "added"}
    finally:
        conn.close()


@app.delete("/groups/{group_name}/members/{bot_name}")
def remove_group_member(group_name: str, bot_name: str, caller: str = Depends(caller_identity)):
    require_admin(caller)
    conn = connect()
    try:
        with conn:
            cur = conn.execute(
                "DELETE FROM group_members WHERE group_name=? AND bot_name=?",
                (group_name, bot_name),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Not a member of this group")
        return {"group": group_name, "bot": bot_name, "status": "removed"}
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
