import time

from fastapi.testclient import TestClient

VALID_KEY = "a" * 32
HEADERS = {"X-API-Key": VALID_KEY}


def test_health_without_key(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_protected_endpoint_without_key_is_rejected(client):
    r = client.get("/msg/pending/eddie")
    assert r.status_code == 403


def test_protected_endpoint_with_wrong_key_is_rejected(client):
    r = client.get("/msg/pending/eddie", headers={"X-API-Key": "b" * 32})
    assert r.status_code == 403


def test_send_pending_respond_status_flow(client):
    r = client.post(
        "/msg/send",
        headers=HEADERS,
        json={"from_bot": "eddie", "to_bot": "marvin", "body": "hi", "subject": "s"},
    )
    assert r.status_code == 200
    msg_id = r.json()["id"]
    assert r.json()["status"] == "pending"

    r = client.get("/msg/pending/marvin", headers=HEADERS)
    assert r.status_code == 200
    messages = r.json()["messages"]
    assert len(messages) == 1
    assert messages[0]["id"] == msg_id
    assert messages[0]["body"] == "hi"

    r = client.post(
        f"/msg/respond/{msg_id}", headers=HEADERS, json={"response_text": "ok"}
    )
    assert r.status_code == 200
    assert r.json() == {"id": msg_id, "status": "done"}

    # nach dem Beantworten nicht mehr in der pending-Liste
    r = client.get("/msg/pending/marvin", headers=HEADERS)
    assert r.json()["messages"] == []

    r = client.get(f"/msg/status/{msg_id}", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["status"] == "done"
    assert r.json()["response_text"] == "ok"


def test_respond_twice_is_rejected(client):
    msg_id = client.post(
        "/msg/send",
        headers=HEADERS,
        json={"from_bot": "eddie", "to_bot": "marvin", "body": "hi"},
    ).json()["id"]

    r = client.post(f"/msg/respond/{msg_id}", headers=HEADERS, json={"response_text": "ok"})
    assert r.status_code == 200

    r = client.post(f"/msg/respond/{msg_id}", headers=HEADERS, json={"response_text": "again"})
    assert r.status_code == 404


def test_status_unknown_id(client):
    r = client.get("/msg/status/9999", headers=HEADERS)
    assert r.status_code == 404


def test_cancel_pending_message(client):
    msg_id = client.post(
        "/msg/send",
        headers=HEADERS,
        json={"from_bot": "eddie", "to_bot": "marvin", "body": "hi"},
    ).json()["id"]

    r = client.delete(f"/msg/{msg_id}", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == {"id": msg_id, "status": "cancelled"}

    # nicht mehr pending
    r = client.get("/msg/pending/marvin", headers=HEADERS)
    assert r.json()["messages"] == []

    # kann nicht mehr beantwortet werden
    r = client.post(f"/msg/respond/{msg_id}", headers=HEADERS, json={"response_text": "ok"})
    assert r.status_code == 404


def test_cancel_unknown_or_already_done_message(client):
    r = client.delete("/msg/9999", headers=HEADERS)
    assert r.status_code == 404

    msg_id = client.post(
        "/msg/send",
        headers=HEADERS,
        json={"from_bot": "eddie", "to_bot": "marvin", "body": "hi"},
    ).json()["id"]
    client.post(f"/msg/respond/{msg_id}", headers=HEADERS, json={"response_text": "ok"})

    r = client.delete(f"/msg/{msg_id}", headers=HEADERS)
    assert r.status_code == 404


def test_pending_limit(client):
    for i in range(5):
        client.post(
            "/msg/send",
            headers=HEADERS,
            json={"from_bot": "eddie", "to_bot": "marvin", "body": f"msg{i}"},
        )

    r = client.get("/msg/pending/marvin", headers=HEADERS, params={"limit": 2})
    assert r.status_code == 200
    assert len(r.json()["messages"]) == 2

    r = client.get("/msg/pending/marvin", headers=HEADERS, params={"limit": 0})
    assert r.status_code == 422


def test_cleanup_removes_old_done_messages(crossbot_env):
    with TestClient(crossbot_env.app) as c:
        msg_id = c.post(
            "/msg/send",
            headers=HEADERS,
            json={"from_bot": "eddie", "to_bot": "marvin", "body": "old"},
        ).json()["id"]
        c.post(f"/msg/respond/{msg_id}", headers=HEADERS, json={"response_text": "ok"})

    # completed_at in die Vergangenheit verschieben, um Retention zu simulieren
    conn = crossbot_env.connect()
    try:
        with conn:
            conn.execute(
                "UPDATE outbox SET completed_at=? WHERE id=?",
                (int(time.time()) - 999_999, msg_id),
            )
        crossbot_env.RETENTION_DAYS = 1
        deleted = crossbot_env.cleanup_old_messages()
        assert deleted == 1

        row = conn.execute("SELECT * FROM outbox WHERE id=?", (msg_id,)).fetchone()
        assert row is None
        row = conn.execute(
            "SELECT * FROM response_log WHERE outbox_id=?", (msg_id,)
        ).fetchone()
        assert row is None
    finally:
        conn.close()
