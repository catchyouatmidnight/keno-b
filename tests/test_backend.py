import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from scripts.database import snapshot, validate


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "keno.db")
    monkeypatch.setattr(main, "API_KEY", "test-key-" + "x" * 40)
    with TestClient(main.app) as client:
        client.headers["Authorization"] = "Bearer " + main.API_KEY
        yield client


def fake_model(mode="ok", seen=None):
    def handler(request):
        payload = json.loads(request.content) if request.content else {}
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if mode == "offline":
            raise httpx.ConnectError("offline", request=request)
        if request.url.path == "/apply-template":
            if seen is not None:
                seen.append(payload["messages"])
            return httpx.Response(200, json={"prompt": json.dumps(payload["messages"])})
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"tokens": list(range(len(payload["content"]) // 3))})
        if request.url.path == "/v1/chat/completions":
            if mode == "failure":
                return httpx.Response(500, json={"error": "failed"})
            chunks = ["Hello ", "Zain"]
            body = "".join('data: ' + json.dumps({"choices": [{"delta": {"content": chunk}, "finish_reason": None}]}) + '\n\n' for chunk in chunks)
            if mode != "interrupted":
                body += 'data: ' + json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}]}) + '\n\ndata: [DONE]\n\n'
            return httpx.Response(200, text=body, headers={"Content-Type": "text/event-stream"})
        raise AssertionError(request.url)
    return httpx.AsyncClient(base_url="http://llm:8080", transport=httpx.MockTransport(handler))


def new_conversation(client):
    return client.post("/api/v1/conversations", json={"title": "Test"}).json()["id"]


def send(client, conversation, **kwargs):
    return client.post("/api/v1/chat", json={"conversation_id": conversation, "message": "Hi", "request_id": "request-0001", **kwargs})


def test_fresh_install_auth_and_restart(client):
    assert client.get("/api/v1/profile").json() == {"name": "", "background": "", "preferences": ""}
    assert client.get("/api/v1/memories").json() == []
    assert client.get("/api/v1/conversations").json() == []
    assert client.get("/api/v1/profile", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/").status_code == 200
    assert "script-src 'self'" in client.get("/").headers["content-security-policy"]
    client.put("/api/v1/profile", json={"name": "Zain"})
    main.initialize()
    assert client.get("/api/v1/profile").json()["name"] == "Zain"


def test_memory_correction_expiry_and_cross_chat(client):
    seen = []
    main.app.state.llm = fake_model(seen=seen)
    client.put("/api/v1/memories/language", json={"key": "language", "content": "English", "pinned": True})
    client.put("/api/v1/memories/language", json={"key": "language", "content": "Indonesian", "pinned": True})
    client.put("/api/v1/memories/old", json={"key": "old", "content": "Expired", "pinned": True, "expires_at": "2000-01-01T00:00:00Z"})
    assert len(client.get("/api/v1/memories").json()) == 1
    for index in range(2):
        response = send(client, new_conversation(client), request_id=f"cross-chat-{index}")
        assert response.status_code == 200
        assert response.json()["context"]["memory_keys"] == ["language"]
    prompt = seen[-1][0]["content"]
    assert "Indonesian" in prompt and "English" not in prompt and "Expired" not in prompt
    client.delete("/api/v1/memories/language")
    assert client.get("/api/v1/memories").json() == []


def test_stream_persistence_and_idempotency(client):
    main.app.state.llm = fake_model()
    conversation = new_conversation(client)
    response = send(client, conversation, stream=True)
    assert response.status_code == 200
    assert 'event: delta' in response.text and 'event: done' in response.text
    assert main.app.state.generation_lock.locked() is False
    result = send(client, conversation).json()
    assert result["reply"] == "Hello Zain"
    assert len(client.get(f"/api/v1/conversations/{conversation}").json()["turns"]) == 1
    assert send(client, conversation, message="Different").status_code == 409
    assert "event: done" in send(client, conversation, stream=True).text


@pytest.mark.parametrize("mode", ["failure", "interrupted"])
def test_failures_do_not_save_partial_answers_and_can_retry(client, mode):
    main.app.state.llm = fake_model(mode)
    conversation = new_conversation(client)
    response = send(client, conversation, stream=True)
    assert 'event: error' in response.text
    turn = client.get(f"/api/v1/conversations/{conversation}").json()["turns"][0]
    assert turn["status"] == "failed" and turn["assistant_text"] is None
    assert not main.app.state.generation_lock.locked()
    main.app.state.llm = fake_model()
    assert send(client, conversation).status_code == 200
    assert len(client.get(f"/api/v1/conversations/{conversation}").json()["turns"]) == 1


def test_readiness_limits_and_busy(client):
    main.app.state.llm = fake_model("offline")
    assert client.get("/api/v1/status").json()["model_ready"] is True  # health is independent of inference
    conversation = new_conversation(client)
    assert send(client, conversation).status_code == 503
    assert not main.app.state.generation_lock.locked()
    assert client.post("/api/v1/conversations", content=b"x" * 1_000_001).status_code == 413
    assert send(client, conversation, max_tokens=99999).status_code == 422
    main.app.state.llm = fake_model()
    assert send(client, conversation, message="x" * 7900).status_code == 200
    # Oversized non-Latin input is still budgeted by the local tokenizer.
    client.put("/api/v1/profile", json={"background": "x" * 1500, "preferences": "x" * 1500})
    assert send(client, conversation, request_id="too-long-000", message="x" * 7900, max_tokens=1024).status_code == 422
    assert not main.app.state.generation_lock.locked()


def test_backup_is_consistent_and_private(client, tmp_path):
    client.put("/api/v1/profile", json={"name": "Zain"})
    new_conversation(client)
    response = client.get("/api/v1/backup")
    backup = tmp_path / "backup.sqlite3"
    backup.write_bytes(response.content)
    validate(backup)
    with sqlite3.connect(backup) as c:
        assert json.loads(c.execute("SELECT value FROM settings WHERE key='profile'").fetchone()[0])["name"] == "Zain"
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    other = tmp_path / "restored.sqlite3"
    snapshot(backup, other)
    validate(other)
    assert main.API_KEY.encode() not in backup.read_bytes()
    assert client.get("/api/v1/backup", headers={"Authorization":"Bearer wrong"}).status_code == 401


def test_startup_recovers_running_turns(client):
    conversation = new_conversation(client)
    with main.db() as c:
        c.execute("INSERT INTO turns(request_id,conversation_id,user_text,status,created_at) VALUES (?,?,?,'running',?)", ("interrupted-000", conversation, "Hi", main.now()))
    main.initialize()
    turn = client.get(f"/api/v1/conversations/{conversation}").json()["turns"][0]
    assert turn["status"] == "failed"


def test_busy_and_cancellation_release_slot(client):
    import asyncio
    main.app.state.llm = fake_model()
    conversation_id = new_conversation(client)
    # Mimic an active generation on the same event loop used by TestClient.
    client.portal.call(main.app.state.generation_lock.acquire)
    assert send(client, conversation_id).status_code == 409
    assert client.delete('/api/v1/conversations/' + conversation_id).status_code == 409
    client.portal.call(main.app.state.generation_lock.release)
    value = main.ChatInput(conversation_id=conversation_id, message='Hi', request_id='cancelled-000')
    with main.db() as c:
        c.execute("INSERT INTO turns(request_id,conversation_id,user_text,status,created_at) VALUES (?,?,?,'running',?)", (value.request_id, conversation_id, 'Hi', main.now()))
    async def cancel_stream():
        await main.app.state.generation_lock.acquire()
        generator = main.generate(value, [{'role':'user','content':'Hi'}], {})
        assert (await anext(generator))[0] == 'delta'
        await generator.aclose()
    client.portal.call(cancel_stream)
    assert not main.app.state.generation_lock.locked()
    assert client.get('/api/v1/conversations/' + conversation_id).json()['turns'][0]['status'] == 'failed'
    assert send(client, conversation_id, request_id='after-cancel-000').status_code == 200


def test_restore_cli_requires_opt_in_and_preserves_data(client, tmp_path):
    import os
    import subprocess
    import sys
    client.put('/api/v1/profile', json={'name':'Original owner'})
    source = tmp_path / 'source.sqlite3'
    source.write_bytes(client.get('/api/v1/backup').content)
    destination = tmp_path / 'new-server' / 'keno.db'
    environment = {**os.environ, 'KENO_DB': str(destination)}
    command = [sys.executable, 'scripts/database.py', 'restore', str(source)]
    denied = subprocess.run(command, env=environment, capture_output=True)
    assert denied.returncode != 0 and not destination.exists()
    restored = subprocess.run(command + ['--replace'], env=environment, capture_output=True)
    assert restored.returncode == 0
    validate(destination)
    with sqlite3.connect(destination) as c:
        assert json.loads(c.execute("SELECT value FROM settings WHERE key='profile'").fetchone()[0])['name'] == 'Original owner'
