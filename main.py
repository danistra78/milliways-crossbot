#!/usr/bin/env python3
"""Cross-Bot Message Bus API — fuer Eddie & Marvin."""

import os
import sqlite3
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

DB_PATH = os.environ.get("CROSSBOT_DB_PATH", "/export/hermes-shared/multi_agent_tg_shared.db")
API_KEY = os.environ.get("CROSSBOT_API_KEY", "")
HOST = os.environ.get("CROSSBOT_HOST", "0.0.0.0")
PORT = int(os.environ.get("CROSSBOT_PORT", "9191"))


class SendRequest(BaseModel):
    from_bot: str
    to_bot: str
    subject: str = ""
    body: str


class RespondRequest(BaseModel):
    response_text: str


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, from_bot TEXT,
        to_bot TEXT, subject TEXT, body TEXT, status TEXT DEFAULT 'pending',
        kanban_task_id INTEGER, response_text TEXT, completed_at INTEGER
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS response_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER,
        outbox_id INTEGER, bot_name TEXT, response TEXT
    )""")
    conn.commit()
    return conn


def verify_key(x_api_key: str = Header(None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_db().close()
    yield

app = FastAPI(title="Cross-Bot Message Bus", version="1.0", lifespan=lifespan)


@app.post("/msg/send")
def send_msg(req: SendRequest, x_api_key: str = Header(None)):
    verify_key(x_api_key)
    conn = get_db()
    try:
        now = int(time.time())
        cur = conn.execute(
            "INSERT INTO outbox (ts, from_bot, to_bot, subject, body, status) VALUES (?, ?, ?, ?, ?, 'pending')",
            (now, req.from_bot, req.to_bot, req.subject, req.body),
        )
        conn.commit()
        return {"id": cur.lastrowid, "status": "pending"}
    finally:
        conn.close()


@app.get("/msg/pending/{bot_name}")
def get_pending(bot_name: str, x_api_key: str = Header(None)):
    verify_key(x_api_key)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, ts, from_bot, to_bot, subject, body, status FROM outbox WHERE to_bot=? AND status='pending' ORDER BY ts ASC",
            (bot_name,),
        ).fetchall()
        return {"messages": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.post("/msg/respond/{msg_id}")
def respond(msg_id: int, req: RespondRequest, x_api_key: str = Header(None)):
    verify_key(x_api_key)
    conn = get_db()
    try:
        now = int(time.time())
        cur = conn.execute(
            "UPDATE outbox SET status='done', response_text=?, completed_at=? WHERE id=? AND status='pending'",
            (req.response_text, now, msg_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Not found or already answered")
        msg = conn.execute("SELECT from_bot, to_bot FROM outbox WHERE id=?", (msg_id,)).fetchone()
        conn.execute(
            "INSERT INTO response_log (ts, outbox_id, bot_name, response) VALUES (?, ?, ?, ?)",
            (now, msg_id, msg["to_bot"], req.response_text),
        )
        conn.commit()
        return {"id": msg_id, "status": "done"}
    finally:
        conn.close()


@app.get("/msg/status/{msg_id}")
def get_status(msg_id: int, x_api_key: str = Header(None)):
    verify_key(x_api_key)
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM outbox WHERE id=?", (msg_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        return dict(row)
    finally:
        conn.close()


@app.get("/health")
def health():
    conn = get_db()
    try:
        conn.execute("SELECT 1")
        return {"status": "ok", "db": DB_PATH}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
