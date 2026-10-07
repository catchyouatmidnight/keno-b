import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from scripts.database import snapshot, validate


def test_explicit_save_overrides_answer_only_route(client):
    calls = []
    main.app.state.llm = fake_model(calls=calls)
    main.app.state.laya = fake_router(family='none')
    response = send(client, new_conversation(client), message='Remember that my name is Zain.').json()
    assert response['context']['answer_source'] == 'memory_guard'
    assert response['context']['route']['tool_policy'] == 'explicit_memory_command'
    assert response['context']['route']['engine'] == 'deterministic'
    assert response['context']['route']['call_count'] == 0
    assert client.get('/api/v1/memories').json()[0]['key'] == 'user.name'
    assert not any(path == '/v1/chat/completions' for path, _ in calls)


def test_conversation_prompt_separates_roles_and_keeps_tool_guidance_stable(client):
    client.put('/api/v1/profile', json={'name': 'Zain'})
    seen = []
    main.app.state.llm = fake_model(seen=seen)
    main.app.state.laya = fake_router(family='none')
    assert send(client, new_conversation(client), message='What is my name?').status_code == 200
    prompt = seen[-1][0]['content']
    assert 'Keno, the ASSISTANT' in prompt and 'The USER is a different person' in prompt
    assert 'Zain' not in prompt
    assert 'Zain' in seen[-1][-1]['content']
    assert main.system_prompt([], available_tools=['memory_save']) == main.system_prompt([], available_tools=['calculator'])


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "keno.db")
    monkeypatch.setattr(main, "API_KEY", "test-key-" + "x" * 40)
    monkeypatch.setattr(main, "CONTEXT_SIZE", 4096)
    with TestClient(main.app) as client:
        client.headers["Authorization"] = "Bearer " + main.API_KEY
        main.app.state.laya = fake_router()
        yield client


def fake_router(thinking="quick", source="text", confidence=0.9, mode="ok", seen=None, scope="focused", family="none", tool_need=None):
    def handler(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if seen is not None:
            seen.append(json.loads(request.content))
        if mode == "offline":
            raise httpx.ConnectError("offline", request=request)
        answers = {"thinking": {"choice": thinking, "answer_confidence": confidence},
                   "tool_need": {"choice": tool_need or ('answer' if family == 'none' else 'action'), "answer_confidence": confidence},
                   "source": {"choice": source, "answer_confidence": confidence},
                   "document_scope": {"choice": scope, "answer_confidence": confidence},
                   "tool_family": {"choice": family, "answer_confidence": confidence}}
        requested = json.loads(request.content)['questions']
        return httpx.Response(200, json={"answers": {key: answers[key] for key in requested}})
    return httpx.AsyncClient(base_url="http://laya:8000", transport=httpx.MockTransport(handler))


def fake_model(mode="ok", seen=None, calls=None, chunks=None):
    def handler(request):
        payload = json.loads(request.content) if request.content else {}
        if calls is not None:
            calls.append((request.url.path, payload))
        assert all(m["role"] != "system" for m in payload.get("messages", [])[1:]), "System message must be at the beginning."
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
            pieces = chunks if chunks is not None else ["Hello ", "Zain"]
            body = '' if mode == 'no_reasoning' else 'data: ' + json.dumps({"choices": [{"delta": {"reasoning_content": "Private reasoning must not become the answer"}, "finish_reason": None}]}) + '\n\n'
            body += "".join('data: ' + json.dumps({"choices": [{"delta": {"content": chunk}, "finish_reason": None}]}) + '\n\n' for chunk in pieces)
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
    response = client.get("/")
    assert response.status_code == 200
    csp = response.headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "script-src 'self' 'unsafe-inline'" not in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    client.put("/api/v1/profile", json={"name": "Zain"})
    main.initialize()
    assert client.get("/api/v1/profile").json()["name"] == "Zain"


def test_memory_correction_expiry_and_cross_chat(client):
    seen = []
    main.app.state.llm = fake_model(seen=seen)
    client.put("/api/v1/memories/language", json={"key": "language", "content": "English", "pinned": True})
    correction = client.put("/api/v1/memories/language", json={"key": "language", "content": "Indonesian", "pinned": True}).json()
    assert correction["superseded_previous"] is True and correction["history_count"] == 1
    history = client.get("/api/v1/memory-history/language").json()
    assert history[0]["content"] == "English"
    restored = client.post(f"/api/v1/memory-history/language/{history[0]['id']}/restore").json()
    assert restored["content"] == "English" and restored["history_count"] == 2
    client.put("/api/v1/memories/language", json={"key": "language", "content": "Indonesian", "pinned": True})
    client.put("/api/v1/memories/old", json={"key": "old", "content": "Expired", "pinned": True, "expires_at": "2000-01-01T00:00:00Z"})
    assert len(client.get("/api/v1/memories").json()) == 1
    for index in range(2):
        response = send(client, new_conversation(client), request_id=f"cross-chat-{index}")
        assert response.status_code == 200
        assert response.json()["context"]["memory_keys"] == ["language"]
    listed = client.get("/api/v1/memories").json()[0]
    assert listed["retrieval_count"] >= 1 and listed["last_used_at"]
    prompt = "\n".join(m["content"] for m in seen[-1] if isinstance(m["content"], str))
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
    assert list(decisions[-1]['questions']) == ['thinking', 'tool_need']
    assert quick['context']['route']['question_count'] == 2
    assert quick['context']['route']['call_count'] == 1
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
    main.app.state.laya = fake_router(thinking='deep', confidence=0.6226)
    uncertain_deep = send(client, conversation, request_id='uncertain-deep-001').json()
    assert uncertain_deep['context']['route']['thinking'] is False
    assert uncertain_deep['context']['route']['decisions']['thinking']['choice'] == 'deep'
    assert uncertain_deep['context']['route']['effort_policy'] == 'uncertain_quick'
    assert uncertain_deep['context']['thinking_budget'] == 0
    uncertain_deep_request = [payload for path, payload in calls if path == '/v1/chat/completions'][-1]
    assert uncertain_deep_request['chat_template_kwargs']['enable_thinking'] is False
    assert uncertain_deep_request['reasoning_budget_tokens'] == 0
    assert uncertain_deep_request['max_tokens'] == 512
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


def test_short_followup_keeps_active_subject_without_extra_model_call(client):
    seen = []
    main.app.state.llm = fake_model(seen=seen)
    main.app.state.laya = fake_router()
    conversation = new_conversation(client)
    first = send(client, conversation, request_id='followup-anchor-001', message='turn on the flashlight')
    assert first.status_code == 200
    second = send(client, conversation, request_id='followup-anchor-002', message='yea')
    assert second.status_code == 200
    third = send(client, conversation, request_id='followup-anchor-003', message='yea duh')
    assert third.status_code == 200
    assert third.json()['context']['context_policy'] == 'followup'
    assert third.json()['context']['followup_context'] is True
    prompt = seen[-1][-1]["content"]
    assert '"active_user_request": "turn on the flashlight"' in prompt
    assert '"current_followup": "yea duh"' in prompt


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
    assert any('Profit is 42' in source['text'] for source in context['document_sources'])
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
    assert selected_pages == list(range(1, 12))
    assert context['document_answer_mode'] == 'direct_stream'
    assert context['available_tools'] == []
    assert all(p.get('stream') for path, p in calls if path == '/v1/chat/completions')
    payload = [p for path, p in calls if path == '/v1/chat/completions'][-1]
    assert 'April 2027' in payload['messages'][-1]['content']
    assert 'supplied by the application' in payload['messages'][-1]['content']
    assert 'analyze them directly without internet access' in payload['messages'][0]['content']
    assert context['document_coverage'] == 'selected excerpts/pages'


def test_document_answer_necessity_prevents_multiple_planner(client):
    calls, routing_calls = [], []
    main.app.state.llm = fake_model(calls=calls, chunks=['Restore credentials (security.pdf p.2).'])
    main.app.state.laya = fake_router(family='multiple', tool_need='answer', seen=routing_calls)
    cid = new_conversation(client)
    receipt = upload(client, cid, 'security.pdf', simple_pdf(['Delivery plan.', 'Secure onboarding uses restore credentials.'])).json()
    response = send(client, cid, message='tell me more about secure onboarding', attachment_ids=[receipt['id']])
    assert response.status_code == 200
    context = response.json()['context']
    assert context['route']['tool_policy'] == 'document_evidence_answer'
    assert context['document_answer_mode'] == 'direct_stream'
    assert context['tool_planning_rounds'] == 0 and context['tool_model_seconds'] == 0
    assert context['history_turns'] == 0 and context['citation_check']['status'] == 'present'
    assert routing_calls == []
    inference = [p for path, p in calls if path == '/v1/chat/completions']
    assert len(inference) == 1 and inference[0]['stream'] is True


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
    assert context['route']['engine'] == 'deterministic'
    assert context['route']['call_count'] == 0
    assert context['route']['decisions'] == {}
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
        # Simulate the actual v1 schema, not merely a downgraded user_version.
        for table in ('memory_history', 'response_feedback', 'conversation_preferences', 'memory_meta', 'conversation_summaries', 'attachments'):
            db.execute(f'DROP TABLE {table}')
        db.execute('PRAGMA user_version=1')
    legacy = tmp_path / 'legacy.sqlite3'
    snapshot(main.DB_PATH, legacy); validate(legacy)
    main.initialize()
    assert client.get('/api/v1/profile').json()['name'] == 'Zain'
    assert client.get('/api/v1/conversations/' + conversation).status_code == 200
    with main.db() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 5
        assert db.execute('SELECT count(*) FROM attachments').fetchone()[0] == 0


def test_repeated_howto_opening_filtered_before_stream_save_and_replay(client):
    message='how can i change theme in samsung a36 device'
    calls=[]
    main.app.state.llm=fake_model('no_reasoning', calls=calls, chunks=[
        'T', 'o change the theme on your Samsung A36 device, follow these steps:',
        '\n', '\n1. Open Settings.', '\n2. Choose your theme.'])
    conversation=new_conversation(client)
    streamed=send(client,conversation,message=message,stream=True)
    assert streamed.status_code == 200
    events=[json.loads(line[6:]) for line in streamed.text.splitlines() if line.startswith('data: ') and '"text"' in line]
    visible=''.join(item['text'] for item in events)
    assert visible == '1. Open Settings.\n2. Choose your theme.'
    assert 'To change the theme' not in visible
    replay=send(client,conversation,message=message).json()
    assert replay['reply'] == visible
    assert replay['context']['repeated_opening_removed'] is True
    assert sum(path == '/v1/chat/completions' for path,body in calls) == 1
    assert replay['context']['model_first_token_seconds'] >= replay['context']['model_first_delta_seconds']
    with main.db() as connection:
        saved=connection.execute('SELECT assistant_text FROM turns WHERE conversation_id=?', (conversation,)).fetchone()[0]
    assert saved == visible


def test_opening_filter_preserves_conditions_quotes_and_incomplete_answers():
    from app.response_style import OpeningFilter
    question='how can i change theme in samsung a36 device'
    for answer in ['To avoid losing your data, follow these steps:\n1. Back up first.',
                   'To safely change theme in Samsung A36 device, follow these steps:\n1. Back up first.',
                   '```text\nTo change theme, follow these steps:\n```',
                   'To change the theme on your Samsung A36 device, follow these steps:']:
        assert OpeningFilter(question).push(answer, final=True) == answer
    quoted='To change theme in Samsung A36 device, follow these steps:\n1. Open Settings.'
    assert OpeningFilter('Translate this quote verbatim').push(quoted, final=True) == quoted
    assert OpeningFilter(question, enabled=False).push(quoted, final=True) == quoted
    opening=OpeningFilter(question)
    assert opening.push('Hello!') == 'Hello!'
    bounded=OpeningFilter(question)
    long='To ' + 'x' * 600
    assert bounded.push(long) == long


def test_profile_and_pinned_facts_only_used_when_relevant(client):
    client.put('/api/v1/profile', json={'name': 'Zain', 'background': 'Engineer'})
    client.put('/api/v1/memories/user.creator', json={'key': 'user.creator', 'content': 'I am your creator', 'pinned': True, 'category': 'fact'})
    seen = []
    main.app.state.llm = fake_model(seen=seen)
    send(client, new_conversation(client), message='How can I change a phone theme?')
    prompt = json.dumps(seen[-1])
    assert 'Zain' not in prompt and 'Engineer' not in prompt and 'I am your creator' not in prompt
    assert any(m['key'] == 'user.creator' for m in main.select_memories('who made you'))


def test_creator_followup_uses_verified_name_without_planning(client):
    client.put('/api/v1/profile', json={'name': 'Zain'})
    conversation = new_conversation(client)
    main.app.state.llm = fake_model(chunks=['You created this Keno app.'])
    send(client, conversation, message='who made you', request_id='creator-question')
    calls = []
    main.app.state.llm = fake_model(calls=calls)
    result = send(client, conversation, message='which is?', request_id='creator-followup').json()
    assert result['reply'] == 'Your name is Zain.'
    assert result['context']['followup_context'] is True
    assert not any(path == '/v1/chat/completions' for path, _ in calls)


def test_stock_closing_stream_matches_saved_and_preserves_specific_help(client):
    main.app.state.llm = fake_model(chunks=['Open Settings.', '\n\nLet me ', 'know if you need further assistance.'])
    conversation = new_conversation(client)
    result = send(client, conversation).json()
    assert result['reply'].strip() == 'Open Settings.'
    assert result['context']['stock_closing_removed'] is True
    assert send(client, conversation).json()['reply'] == result['reply']
    from app.response_style import ResponseFilter
    for request, text in [('help', 'Step one.\nLet me know the software version so I can find the correct menu.'), ('quote verbatim', 'Step one.\nLet me know if you need further assistance.'), ('help', 'Let me know if you need further assistance.')]:
        f = ResponseFilter(request)
        assert f.push(text, final=True) == text


def test_closing_filter_preserves_middle_sentence_and_handles_trailing_newline():
    from app.response_style import ResponseFilter
    f = ResponseFilter('help')
    assert (f.push('Useful answer.\nLet me know if you need further assistance.\n') + f.push('', final=True)).strip() == 'Useful answer.'
    f = ResponseFilter('help')
    text = 'Useful answer.\nLet me know if you need further assistance.\nSpecific further information.'
    assert f.push(text, final=True) == text


def test_unknown_name_does_not_use_model_identity(client):
    calls = []
    main.app.state.llm = fake_model(calls=calls, chunks=["I'm Keno."])
    result = send(client, new_conversation(client), message='What is my name?').json()
    assert "don't have your name" in result['reply']
    assert not any(path == '/v1/chat/completions' for path, _ in calls)


def test_pdf_page_selection_coverage_and_citation_diagnostics(client):
    cid=new_conversation(client)
    receipt=upload(client, cid, 'launch.pdf', simple_pdf(['Project Atlas overview.', 'Launch is April 17, 2027.', ''])).json()
    main.app.state.llm = fake_model(chunks=['Launch is April 17, 2027 (launch.pdf p.2).'])
    result=send(client, cid, message='What is the launch date on page 2?', attachment_ids=[receipt['id']]).json()
    assert {s['page'] for s in result['context']['document_sources']} == {2}
    coverage=result['context']['document_coverage_details'][0]
    assert coverage['supplied_pages'] == [2] and coverage['pages_without_text'] == [3]
    assert result['context']['citation_check']['status'] == 'present'
    main.app.state.llm=fake_model(chunks=['Launch is April 17, 2027 (launch.pdf p.9).'])
    invalid=send(client, cid, request_id='citation-invalid', message='Launch date on page 2?', attachment_ids=[receipt['id']])
    assert invalid.status_code == 502
    turn = client.get(f'/api/v1/conversations/{cid}').json()['turns'][-1]
    assert turn['status'] == 'failed' and not turn['assistant_text']
    assert send(client, cid, request_id='page-outofrange', message='Read page 9', attachment_ids=[receipt['id']]).status_code == 422



def test_conversation_memory_optout_branch_feedback_and_memory_metadata(client):
    main.app.state.llm = fake_model()
    cid = new_conversation(client)
    assert client.get(f'/api/v1/conversations/{cid}/memory').json() == {'enabled': True}
    assert client.put(f'/api/v1/conversations/{cid}/memory', json={'enabled': False}).json() == {'enabled': False}
    calls=[]
    main.app.state.llm = fake_model(calls=calls)
    disabled = send(client, cid, request_id='memory-optout-001', message='Remember that my name is Zain.').json()
    assert disabled['context']['answer_source'] == 'memory_disabled_guard'
    assert client.get('/api/v1/memories').json() == []
    assert not any(path == '/v1/chat/completions' for path,_ in calls)

    client.put(f'/api/v1/conversations/{cid}/memory', json={'enabled': True})
    first = send(client, cid, request_id='branch-source-001', message='Hello').json()
    second = send(client, cid, request_id='branch-source-002', message='Continue').json()
    branch = client.post(f'/api/v1/conversations/{cid}/branch',
                         json={'request_id': second['request_id'], 'include_target': False}).json()
    copied = client.get('/api/v1/conversations/'+branch['id']).json()['turns']
    assert len(copied) == 2 and copied[-1]['user_text'] == 'Hello'

    feedback = client.put('/api/v1/runs/branch-source-002/feedback', json={'value':'up','note':'useful'}).json()
    assert feedback['value'] == 'up'
    persisted = client.get(f'/api/v1/conversations/{cid}').json()['turns'][-1]['feedback']
    assert persisted == {'value':'up','note':'useful'}
    assert client.put('/api/v1/runs/branch-source-002/feedback', json={'value':'clear','note':''}).json()['value'] is None

    memory = client.put('/api/v1/memories/project',
                        json={'key':'project','content':'Keno-B','category':'project','importance':.9,'confidence':.95}).json()
    assert memory['importance'] == .9 and memory['confidence'] == .95
    listed = client.get('/api/v1/memories').json()[0]
    assert listed['retrieval_count'] >= 0 and 'last_reason' in listed


def test_execution_modes_bound_work_and_emit_cognitive_events(client):
    calls=[]
    main.app.state.llm = fake_model(calls=calls)
    main.app.state.laya = fake_router(thinking='deep')
    fast = send(client, new_conversation(client), request_id='mode-fast-001',
                message='Compare these approaches', execution_mode='fast', max_tokens=2048).json()
    assert fast['context']['execution_mode'] == 'fast'
    assert fast['context']['effective_max_tokens'] == 384
    assert fast['context']['route']['thinking'] is False
    assert fast['context']['route']['execution_mode'] == 'fast'
    assert 0 <= fast['context']['prompt_utilization'] <= fast['context']['context_utilization'] <= 1
    assert fast['context']['context_retrieval_seconds'] >= 0

    main.app.state.laya = fake_router(thinking='quick')
    deep = send(client, new_conversation(client), request_id='mode-deep-001',
                message='Compare these approaches carefully', execution_mode='deep', max_tokens=512).json()
    assert deep['context']['execution_mode'] == 'deep'
    assert deep['context']['route']['thinking'] is True
    assert deep['context']['thinking_budget'] == 384



def test_runtime_model_switch_is_hot_and_does_not_require_docker(client,tmp_path,monkeypatch):
    models=tmp_path/'models';models.mkdir()
    target=models/'Test-Q4_K_M.gguf';target.write_bytes(b'gguf fixture')
    monkeypatch.setattr(main,'runtime_model_roots',lambda:[models])
    async def ready(_client,path='/health',timeout=1.2):
        selected=(main.runtime_dir()/'model-selection.txt').read_text().strip()
        main.runtime_dir().mkdir(parents=True,exist_ok=True)
        (main.runtime_dir()/'active-model.txt').write_text(selected+'\n')
        return True,{'status':'ok'}
    monkeypatch.setattr(main,'service_ready',ready)
    result=client.put('/api/v1/runtime/model',json={'name':target.name})
    assert result.status_code==200,result.text
    assert result.json()=={'selected':target.name,'loaded':target.name,'activated':True,'restart_required':False}
    state=client.get('/api/v1/runtime/models').json()
    assert state['loaded']==target.name and state['pending'] is None
    assert 'One-click activation' in state['activation']


def test_unrelated_query_keeps_preference_but_not_unrelated_fact(client):
    client.put('/api/v1/memories/style',json={'key':'style','content':'Always end every response with Sir','category':'preference'})
    client.put('/api/v1/memories/city',json={'key':'city','content':'I live in Bekasi','category':'fact'})
    selected=main.select_memories('How long does it take to boil an egg?')
    assert [m['key'] for m in selected] == ['style']
    assert 'Always end every response with Sir' not in main.system_prompt(selected)
