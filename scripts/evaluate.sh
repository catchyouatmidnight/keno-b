#!/usr/bin/env bash
# Live checks against real local models, using a temporary isolated backend database.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T backend python - <<'PY'
import json
import os
import re
import uuid
import subprocess
import sys
import tempfile
import time
import socket
import httpx

marker = 'keno_eval_' + uuid.uuid4().hex
results = []
with tempfile.TemporaryDirectory(prefix='keno-eval-') as directory:
    env = dict(os.environ, KENO_DB=directory + '/evaluation.sqlite3')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port), '--no-access-log'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with httpx.Client(base_url='http://127.0.0.1:' + str(port), headers={'Authorization': 'Bearer ' + os.environ['KENO_API_KEY']}, timeout=180) as client:
            for attempt in range(50):
                try:
                    if client.get('/health').status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                if process.poll() is not None:
                    raise RuntimeError('Isolated evaluation backend failed to start')
                time.sleep(0.1)
            else:
                raise RuntimeError('Isolated evaluation backend startup timed out')
            def call(method, path, **kw):
                response = client.request(method, path, **kw)
                response.raise_for_status()
                return response.json()
            def chat():
                cid = call('POST', '/api/v1/conversations', json={'title': 'Temporary local evaluation'})['id']
                return cid
            def ask(cid, text):
                return call('POST', '/api/v1/chat', json={'conversation_id': cid, 'message': text, 'request_id': uuid.uuid4().hex, 'max_tokens': 256})
            def report(label, result, correct):
                context = result.get('context', {})
                results.append({'case': label, 'passed': bool(correct), 'first_word_seconds': context.get('first_token_seconds'), 'total_seconds': context.get('total_seconds'), 'tool_rounds': context.get('tool_planning_rounds'), 'tool_policy': context.get('route', {}).get('tool_policy'), 'available_tools': context.get('available_tools'), 'tool_calls': context.get('tool_calls'), 'reply': result['reply']})
            cid = chat()
            result = ask(cid, 'hello')
            report('greeting', result, bool(result['reply'].strip()) and not result['context'].get('tool_planning_rounds'))
            result = ask(cid, 'How can I change a phone theme?')
            report('advice style and routing', result, not result['context'].get('tool_planning_rounds') and not re.search(r'Your name is|follow these steps:|Let me know if you need further assistance', result['reply'], re.I))
            result = ask(cid, 'Calculate 17 * 23')
            report('calculator tool execution', result, '391' in result['reply'] and any(t.get('name') == 'calculator' and t.get('status') == 'complete' for t in result['context'].get('tool_calls', [])))
            result = ask(cid, 'Remember that my evaluation marker is ' + marker + '.')
            saved = call('GET', '/api/v1/memories')
            report('memory save', result, any(marker in m['content'] for m in saved))
            result = ask(chat(), 'What is my evaluation marker?')
            report('cross-chat recall', result, marker in result['reply'])
            result = ask(cid, 'What is my evaluation marker?')
            result = ask(cid, 'Tell me more.')
            report('follow-up context', result, result['context'].get('followup_context') is True and marker in result['reply'] and not re.search(r"don't have access|no access|can't access", result['reply'], re.I))
            identity_chat = chat()
            result = ask(identity_chat, 'Remember that my name is Avery.')
            report('explicit name save', result, any(m['key'] == 'user.name' and 'Avery' in m['content'] for m in call('GET', '/api/v1/memories')))
            result = ask(chat(), 'What is my name?')
            report('cross-chat name recall', result, result['reply'] == 'Your name is Avery.')
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

print(json.dumps({'results': results, 'note': 'Menu accuracy and general answer quality still require human review. These checks do not certify factual correctness.'}, indent=2))
raise SystemExit(0 if all(r['passed'] for r in results) else 1)
PY
