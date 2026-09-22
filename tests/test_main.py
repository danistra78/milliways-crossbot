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


def register(client, name):
    r = client.post("/bots", headers=HEADERS, json={"name": name})
    assert r.status_code == 200
    return {"X-API-Key": r.json()["api_key"]}


def test_register_bot_requires_admin(client):
    eddie = register(client, "eddie")
    r = client.post("/bots", headers=eddie, json={"name": "marvin"})
    assert r.status_code == 403


def test_register_duplicate_bot_is_rejected(client):
    register(client, "eddie")
    r = client.post("/bots", headers=HEADERS, json={"name": "eddie"})
    assert r.status_code == 409


def test_bot_scoped_key_can_only_send_as_self(client):
    eddie = register(client, "eddie")
    register(client, "marvin")

    r = client.post(
        "/msg/send", headers=eddie,
        json={"from_bot": "eddie", "to_bot": "marvin", "body": "hi"},
    )
    assert r.status_code == 200

    r = client.post(
        "/msg/send", headers=eddie,
        json={"from_bot": "marvin", "to_bot": "eddie", "body": "spoofed"},
    )
    assert r.status_code == 403


def test_bot_scoped_key_can_only_fetch_own_inbox(client):
    eddie = register(client, "eddie")
    marvin = register(client, "marvin")
    client.post(
        "/msg/send", headers=HEADERS,
        json={"from_bot": "eddie", "to_bot": "marvin", "body": "hi"},
    )

    r = client.get("/msg/pending/eddie", headers=marvin)
    assert r.status_code == 403

    r = client.get("/msg/pending/marvin", headers=marvin)
    assert r.status_code == 200
    assert len(r.json()["messages"]) == 1


def test_bot_scoped_key_can_only_respond_to_own_messages(client):
    eddie = register(client, "eddie")
    marvin = register(client, "marvin")
    msg_id = client.post(
        "/msg/send", headers=HEADERS,
        json={"from_bot": "eddie", "to_bot": "marvin", "body": "hi"},
    ).json()["id"]

    r = client.post(f"/msg/respond/{msg_id}", headers=eddie, json={"response_text": "nope"})
    assert r.status_code == 403

    r = client.post(f"/msg/respond/{msg_id}", headers=marvin, json={"response_text": "ok"})
    assert r.status_code == 200


def test_bot_scoped_key_can_only_cancel_own_sent_messages(client):
    eddie = register(client, "eddie")
    marvin = register(client, "marvin")
    msg_id = client.post(
        "/msg/send", headers=HEADERS,
        json={"from_bot": "eddie", "to_bot": "marvin", "body": "hi"},
    ).json()["id"]

    r = client.delete(f"/msg/{msg_id}", headers=marvin)
    assert r.status_code == 403

    r = client.delete(f"/msg/{msg_id}", headers=eddie)
    assert r.status_code == 200


def test_revoked_bot_key_no_longer_works(client):
    eddie = register(client, "eddie")
    r = client.delete("/bots/eddie", headers=HEADERS)
    assert r.status_code == 200

    r = client.get("/msg/pending/eddie", headers=eddie)
    assert r.status_code == 403


def test_broadcast_via_group(client):
    register(client, "eddie")
    register(client, "marvin")
    register(client, "ford")

    client.put("/groups/ops/members/eddie", headers=HEADERS)
    client.put("/groups/ops/members/marvin", headers=HEADERS)

    r = client.post(
        "/msg/send", headers=HEADERS,
        json={"from_bot": "ford", "to_group": "ops", "body": "achtung"},
    )
    assert r.status_code == 200
    assert sorted(r.json()["ids"]) == r.json()["ids"]
    assert len(r.json()["ids"]) == 2

    for bot in ("eddie", "marvin"):
        pending = client.get(f"/msg/pending/{bot}", headers=HEADERS).json()["messages"]
        assert len(pending) == 1
        assert pending[0]["body"] == "achtung"


def test_send_requires_exactly_one_of_to_bot_or_to_group(client):
    register(client, "eddie")
    r = client.post(
        "/msg/send", headers=HEADERS,
        json={"from_bot": "eddie", "body": "hi"},
    )
    assert r.status_code == 400

    r = client.post(
        "/msg/send", headers=HEADERS,
        json={"from_bot": "eddie", "to_bot": "marvin", "to_group": "ops", "body": "hi"},
    )
    assert r.status_code == 400


def test_send_to_unknown_group_is_rejected(client):
    register(client, "eddie")
    r = client.post(
        "/msg/send", headers=HEADERS,
        json={"from_bot": "eddie", "to_group": "does-not-exist", "body": "hi"},
    )
    assert r.status_code == 404


def test_group_membership_management(client):
    register(client, "eddie")
    r = client.put("/groups/ops/members/eddie", headers=HEADERS)
    assert r.status_code == 200

    r = client.get("/groups", headers=HEADERS)
    assert r.json()["groups"] == ["ops"]

    r = client.get("/groups/ops/members", headers=HEADERS)
    assert r.json()["members"] == ["eddie"]

    r = client.delete("/groups/ops/members/eddie", headers=HEADERS)
    assert r.status_code == 200

    r = client.get("/groups/ops/members", headers=HEADERS)
    assert r.json()["members"] == []


def test_group_membership_management_requires_admin(client):
    eddie = register(client, "eddie")
    r = client.put("/groups/ops/members/eddie", headers=eddie)
    assert r.status_code == 403
