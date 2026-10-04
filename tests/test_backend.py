import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from scripts.database import snapshot, validate


def test_explicit_save_without_tool_cannot_claim_persistence(client):
    calls = []
    main.app.state.llm = fake_model(calls=calls)
    main.app.state.laya = fake_router(family='none')
    response = send(client, new_conversation(client), message='Remember that my name is Zain.').json()
    assert response['context']['answer_source'] == 'memory_guard'
    assert "It hasn't been saved for future chats" in response['reply']
    assert client.get('/api/v1/memories').json() == []
    assert not any(path == '/v1/chat/completions' for path, _ in calls)


def test_conversation_prompt_separates_roles_and_omits_unavailable_tool_guidance(client):
    client.put('/api/v1/profile', json={'name': 'Zain'})
    seen = []
    main.app.state.llm = fake_model(seen=seen)
    main.app.state.laya = fake_router(family='none')
    assert send(client, new_conversation(client), message='What is my name?').status_code == 200
    prompt = seen[-1][0]['content']
    assert 'Keno, the ASSISTANT' in prompt and 'The USER is a different person' in prompt
    assert 'Zain' in prompt
    assert 'use document_overview' not in prompt
    assert 'Use calculator for arithmetic' not in prompt


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "keno.db")
    monkeypatch.setattr(main, "API_KEY", "test-key-" + "x" * 40)
    monkeypatch.setattr(main, "CONTEXT_SIZE", 4096)
    with TestClient(main.app) as client:
        client.headers["Authorization"] = "Bearer " + main.API_KEY
        main.app.state.laya = fake_router()
        yield client


def fake_router(thinking="quick", source="text", confidence=0.9, mode="ok", seen=None, scope="focused", family="none"):
    def handler(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if seen is not None:
            seen.append(json.loads(request.content))
        if mode == "offline":
            raise httpx.ConnectError("offline", request=request)
        answers = {"thinking": {"choice": thinking, "answer_confidence": confidence},
                   "source": {"choice": source, "answer_confidence": confidence},
                   "document_scope": {"choice": scope, "answer_confidence": confidence},
                   "tool_family": {"choice": family, "answer_confidence": confidence}}
        requested = json.loads(request.content)['questions']
        return httpx.Response(200, json={"answers": {key: answers[key] for key in requested}})
    return httpx.AsyncClient(base_url="http://laya:8000", transport=httpx.MockTransport(handler))


def fake_model(mode="ok", seen=None, calls=None):
    def handler(request):
        payload = json.loads(request.content) if request.content else {}
        if calls is not None:
            calls.append((request.url.path, payload))
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
            body = '' if mode == 'no_reasoning' else 'data: ' + json.dumps({"choices": [{"delta": {"reasoning_content": "Private reasoning must not become the answer"}, "finish_reason": None}]}) + '\n\n'
            body += "".join('data: ' + json.dumps({"choices": [{"delta": {"content": chunk}, "finish_reason": None}]}) + '\n\n' for chunk in chunks)
            if mode != "interrupted":
                body += 'data: ' + json.dumps({"choices": [{"delta": {}, "finish_reason": "length" if mode == "length" else "stop"}]}) + '\n\ndata: [DONE]\n\n'
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
        assert (await anext(generator))[0] == 'timing'
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


def test_long_output_reports_timing_and_truncation(client):
    seen = []
    main.app.state.llm = fake_model("length", seen=seen)
    first = send(client, new_conversation(client), request_id="long-output-001", max_tokens=2048)
    assert first.status_code == 200
    context = first.json()["context"]
    assert context["truncated"] is True and context["finish_reason"] == "length"
    assert context["max_tokens"] == 2048
    assert context["context_prepare_seconds"] >= 0
    assert context["first_token_seconds"] >= context["model_first_token_seconds"] >= 0
    assert context["total_seconds"] >= context["first_token_seconds"]
    second = send(client, new_conversation(client), request_id="long-output-002", max_tokens=2048, stream=True)
    assert "event: timing" in second.text and "event: done" in second.text
    assert seen[0][0]["content"] == seen[-1][0]["content"]


def upload(client, conversation, name, raw):
    import base64
    return client.post('/api/v1/attachments', json={'conversation_id': conversation, 'name': name,
                       'data_base64': base64.b64encode(raw).decode()})


def simple_pdf(texts):
    objects = [b'', b'']
    page_ids = []
    for text in texts:
        page_id = len(objects) + 1
        stream_id = page_id + 1
        font_id = page_id + 2
        page_ids.append(page_id)
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 400] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {stream_id} 0 R >>'.encode())
        stream = ('BT /F1 12 Tf 20 350 Td (' + text + ') Tj ET').encode()
        objects.append(b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream')
        objects.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    objects[0] = b'<< /Type /Catalog /Pages 2 0 R >>'
    objects[1] = ('<< /Type /Pages /Count ' + str(len(page_ids)) + ' /Kids [' + ' '.join(f'{i} 0 R' for i in page_ids) + '] >>').encode()
    body = b'%PDF-1.4\n'
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(body)); body += f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(body)
    body += f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    body += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    body += f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()
    return body


def test_laya_automatically_controls_thinking_and_fails_explicitly(client):
    calls, decisions = [], []
    main.app.state.llm = fake_model(calls=calls)
    conversation = new_conversation(client)
    main.app.state.laya = fake_router(seen=decisions)
    quick = send(client, conversation).json()
    assert quick['context']['route']['thinking'] is False
    assert quick['context']['thinking_budget'] == 0
    main.app.state.laya = fake_router(thinking='deep', seen=decisions)
    deep = send(client, conversation, request_id='deep-analysis-001', message='Compare these two plans and explain the tradeoffs').json()
    assert deep['context']['route']['engine'] == 'laya'
    assert deep['context']['thinking_budget'] == 384
    requests = [payload for path, payload in calls if path == '/v1/chat/completions']
    assert requests[0]['chat_template_kwargs']['enable_thinking'] is False
    assert requests[1]['chat_template_kwargs']['enable_thinking'] is True
    assert requests[1]['max_tokens'] == 896
    assert requests[1]['reasoning_budget_tokens'] == 384
    assert requests[1]['reasoning_format'] == 'deepseek'
    assert 'Hi' in decisions[-1]['state']['earlier_user_requests']
    assert 'Hello Zain' not in decisions[-1]['state']['earlier_user_requests']
    assert list(decisions[-1]['questions']) == ['thinking', 'tool_family']
    assert quick['context']['route']['question_count'] == 2
    assert quick['context']['model_first_delta_seconds'] <= quick['context']['model_first_token_seconds']
    assert quick['context']['model_first_reasoning_seconds'] >= 0
    assert quick['context']['hidden_reasoning_seconds'] >= 0
    main.app.state.laya = fake_router(confidence=0.55)
    uncertain = send(client, conversation, request_id='uncertain-analysis-001').json()
    assert uncertain['context']['route']['thinking'] is False
    assert uncertain['context']['route']['uncertain'] is True
    assert uncertain['context']['thinking_budget'] == 0
    uncertain_request = [payload for path, payload in calls if path == '/v1/chat/completions'][-1]
    assert uncertain_request['chat_template_kwargs']['enable_thinking'] is False
    assert uncertain_request['reasoning_budget_tokens'] == 0
    main.app.state.laya = fake_router(thinking='deep', confidence=0.55)
    uncertain_deep = send(client, conversation, request_id='uncertain-deep-001').json()
    assert uncertain_deep['context']['route']['thinking'] is True
    assert uncertain_deep['context']['thinking_budget'] == 96
    uncertain_deep_request = [payload for path, payload in calls if path == '/v1/chat/completions'][-1]
    assert uncertain_deep_request['chat_template_kwargs']['enable_thinking'] is True
    assert uncertain_deep_request['reasoning_budget_tokens'] == 96
    assert uncertain_deep_request['max_tokens'] == 608
    main.app.state.llm = fake_model('no_reasoning')
    main.app.state.laya = fake_router()
    plain = send(client, conversation, request_id='no-reasoning-001').json()
    assert plain['context']['hidden_reasoning_seconds'] == 0
    assert 'model_first_reasoning_seconds' not in plain['context']
    main.app.state.laya = fake_router(mode='offline')
    assert send(client, conversation, request_id='offline-router-001').status_code == 503
    assert not main.app.state.generation_lock.locked()
    main.app.state.laya = fake_router(thinking='unknown')
    assert send(client, conversation, request_id='invalid-router-001').status_code == 503
    assert send(client, conversation, thinking=True).status_code == 422


def test_document_sources_attachment_isolation_and_backup(client, tmp_path):
    calls = []
    main.app.state.llm = fake_model(calls=calls)
    conversation = new_conversation(client)
    other = new_conversation(client)
    receipt = upload(client, conversation, 'report.pdf', simple_pdf(['Revenue is 100', 'Profit is 42'])).json()
    assert receipt['pages'] == 2 and receipt['characters'] > 0
    response = send(client, conversation, message='What is the profit?', attachment_ids=[receipt['id']])
    assert response.status_code == 200
    context = response.json()['context']
    assert any(source['page'] == 2 for source in context['document_sources'])
    assert context['document_coverage'] == 'selected excerpts/pages'
    payload = [p for path, p in calls if path == '/v1/chat/completions'][-1]
    assert 'Profit is 42' in payload['messages'][-1]['content']
    assert send(client, other, request_id='foreign-file-001', attachment_ids=[receipt['id']]).status_code == 422
    assert send(client, conversation, attachment_ids=[]).status_code == 409
    backup = tmp_path / 'with-files.sqlite3'
    snapshot(main.DB_PATH, backup); validate(backup)
    with sqlite3.connect(backup) as db:
        assert db.execute('SELECT length(raw) FROM attachments').fetchone()[0] > 0
    assert client.delete('/api/v1/conversations/' + conversation).status_code == 200
    with main.db() as db:
        assert db.execute('SELECT count(*) FROM attachments').fetchone()[0] == 0


def test_vague_document_request_samples_later_pages(client):
    calls = []
    main.app.state.llm = fake_model(calls=calls)
    main.app.state.laya = fake_router(scope='focused')
    conversation = new_conversation(client)
    # Common words must not turn a broad request into matches on early pages.
    pages = ['This is the overview.'] * 10 + ['Migration deadline: April 2027.']
    receipt = upload(client, conversation, 'plan.pdf', simple_pdf(pages)).json()
    response = send(client, conversation, message='tell me about this', attachment_ids=[receipt['id']])
    assert response.status_code == 200
    context = response.json()['context']
    selected_pages = [source['page'] for source in context['document_sources']]
    assert selected_pages == [1, 3, 5, 7, 9, 11]
    payload = [p for path, p in calls if path == '/v1/chat/completions'][-1]
    assert 'April 2027' in payload['messages'][-1]['content']
    assert 'supplied by the application' in payload['messages'][-1]['content']
    assert 'analyze them directly without internet access' in payload['messages'][0]['content']
    assert context['document_coverage'] == 'selected excerpts/pages'


def test_vision_is_local_bounded_and_selected_by_laya(client, monkeypatch):
    import io
    from PIL import Image
    monkeypatch.setattr(main, 'VISION_ENABLED', True)
    monkeypatch.setattr(main, 'CONTEXT_SIZE', 8192)
    calls = []
    main.app.state.llm = fake_model(calls=calls)
    main.app.state.laya = fake_router(thinking='deep', source='vision')
    conversation = new_conversation(client)
    receipt = upload(client, conversation, 'scan.pdf', simple_pdf(['', '', ''])).json()
    response = send(client, conversation, message='Explain page 2', attachment_ids=[receipt['id']])
    assert response.status_code == 200
    context = response.json()['context']
    assert context['visual_sources'][0]['page'] == 2
    assert context['route']['question_count'] == 4
    assert set(context['route']['decisions']) == {'thinking', 'source', 'document_scope', 'tool_family'}
    payload = [p for path, p in calls if path == '/v1/chat/completions'][-1]
    parts = payload['messages'][-1]['content']
    assert parts[1]['image_url']['url'].startswith('data:image/jpeg;base64,')
    assert len(parts) == 2
    assert context['image_token_reserve'] == 1088
    assert send(client, conversation, message='Inspect page 99', request_id='bad-page-001').status_code == 422
    raw = io.BytesIO(); Image.new('RGB', (1800, 1200), 'white').save(raw, 'PNG')
    image_receipt = upload(client, conversation, 'photo.png', raw.getvalue()).json()
    # Even an uncertain text decision cannot erase the only available image evidence.
    main.app.state.laya = fake_router(source='text')
    image_response = send(client, conversation, request_id='photo-analysis-001', attachment_ids=[image_receipt['id']])
    assert image_response.json()['context']['route']['vision'] is True
    monkeypatch.setattr(main, 'VISION_ENABLED', False)
    assert upload(client, conversation, 'photo.png', raw.getvalue()).status_code == 422


def test_upload_validation_and_local_docx_extraction(client):
    import io
    import zipfile
    conversation = new_conversation(client)
    assert upload(client, conversation, 'bad.pdf', b'not a PDF').status_code == 422
    assert upload(client, conversation, 'payload.exe', b'bytes').status_code == 422
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Budget 77</w:t></w:r></w:p></w:body></w:document>')
    receipt = upload(client, conversation, 'notes.docx', archive.getvalue()).json()
    assert receipt['characters'] == len('Budget 77')
    invalid = client.post('/api/v1/attachments', json={'conversation_id': conversation, 'name': 'x.txt', 'data_base64': '!not base64'})
    assert invalid.status_code == 422
    assert upload(client, conversation, 'huge.txt', b'x' * (8 * 1024 * 1024 + 1)).status_code == 413
    assert 'data_base64' not in client.get('/api/v1/conversations/' + conversation + '/attachments').text


def test_v1_backup_migrates_without_resetting_personal_state(client, tmp_path):
    client.put('/api/v1/profile', json={'name': 'Zain'})
    conversation = new_conversation(client)
    with main.db() as db:
        db.execute('DROP TABLE attachments')
        db.execute('DROP TABLE conversation_summaries')
        db.execute('PRAGMA user_version=1')
    legacy = tmp_path / 'legacy.sqlite3'
    snapshot(main.DB_PATH, legacy); validate(legacy)
    main.initialize()
    assert client.get('/api/v1/profile').json()['name'] == 'Zain'
    assert client.get('/api/v1/conversations/' + conversation).status_code == 200
    with main.db() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 3
        assert db.execute('SELECT count(*) FROM attachments').fetchone()[0] == 0
