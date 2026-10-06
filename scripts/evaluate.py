import json
import os
import re
import uuid
import subprocess
import sys
import tempfile
import time
import socket
import base64
from pathlib import Path
import httpx

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
            def ask(cid, text, attachment_ids=None):
                try:
                    return call('POST', '/api/v1/chat', json={'conversation_id': cid, 'message': text, 'request_id': uuid.uuid4().hex, 'max_tokens': 256, 'attachment_ids': attachment_ids or []})
                except httpx.HTTPError as error:
                    return {'reply': str(error), 'context': {}, 'evaluation_error': True}
            def report(label, result, correct):
                context = result.get('context', {})
                results.append({'case': label, 'passed': bool(correct) and not result.get('evaluation_error', False), 'first_word_seconds': context.get('first_token_seconds'), 'total_seconds': context.get('total_seconds'), 'tool_rounds': context.get('tool_planning_rounds'), 'tool_policy': context.get('route', {}).get('tool_policy'), 'available_tools': context.get('available_tools'), 'tool_calls': context.get('tool_calls'), 'citation_check': context.get('citation_check'), 'document_coverage': context.get('document_coverage_details'), 'reply': result['reply']})
            cid = chat()
            result = ask(cid, 'hello')
            report('greeting', result, bool(result['reply'].strip()) and not result['context'].get('tool_planning_rounds'))
            result = ask(cid, 'How can I change a phone theme?')
            report('advice style and routing; menu accuracy unverified', result, not result['context'].get('tool_planning_rounds') and not re.search(r'Your name is|follow these steps:|Let me know if you need further assistance', result['reply'], re.I))
            result = ask(cid, 'Calculate 17 * 23')
            report('calculator tool execution', result, '391' in result['reply'] and any(t.get('name') == 'calculator' and t.get('status') == 'complete' for t in result['context'].get('tool_calls', [])))
            result = ask(cid, 'Remember that my evaluation marker is ' + marker + '.')
            saved = call('GET', '/api/v1/memories')
            report('memory save', result, any(marker in m['content'] for m in saved))
            result = ask(chat(), 'What is my evaluation marker?')
            report('cross-chat recall', result, marker in result['reply'])
            result = ask(cid, 'What is my evaluation marker?')
            previous_reply = result['reply']
            result = ask(cid, 'Tell me more.')
            report('follow-up context', result, result['context'].get('followup_context') is True and result['reply'] != previous_reply and marker in result['reply'] and not re.search(r"don't have access|no access|can't access", result['reply'], re.I))
            identity_chat = chat()
            result = ask(identity_chat, 'Remember that my name is Avery.')
            report('explicit name save', result, any(m['key'] == 'user.name' and 'Avery' in m['content'] for m in call('GET', '/api/v1/memories')))
            result = ask(chat(), 'What is my name?')
            report('cross-chat name recall', result, result['reply'] == 'Your name is Avery.')
            reasoning = ask(chat(), 'Lina is taller than Budi. Budi is taller than Maya. Who is shortest? Answer only with the name.')
            report('basic reasoning', reasoning, reasoning['reply'].strip().rstrip('.!').casefold() == 'maya')
            location_chat = chat()
            result = ask(location_chat, 'I live in Bekasi.')
            report('natural location save', result, any(m['key'] == 'user.location' and 'Bekasi' in m['content'] for m in call('GET', '/api/v1/memories')))
            result = ask(location_chat, 'Actually, I moved to Bandung.')
            report('location correction', result, any(m['key'] == 'user.location' and 'Bandung' in m['content'] for m in call('GET', '/api/v1/memories')))
            result = ask(chat(), 'Where do I live?')
            report('location recall', result, result['reply'] == 'You live in Bandung.')
            result = ask(location_chat, 'Forget my city.')
            report('location deletion', result, not any(m['key'] == 'user.location' for m in call('GET', '/api/v1/memories')))
            doc_chat = chat()
            pdf = simple_pdf(['Project Atlas overview.', 'Launch date: April 17, 2027.', ''])
            file = call('POST', '/api/v1/attachments', json={'conversation_id': doc_chat, 'name': 'evaluation.pdf', 'data_base64': base64.b64encode(pdf).decode()})
            result = ask(doc_chat, 'What is the launch date on page 2? Cite the filename and page.', [file['id']])
            report('PDF date and page citation', result, '2027' in result['reply'] and '17' in result['reply'] and 'april' in result['reply'].casefold() and result['context'].get('citation_check', {}).get('status') == 'present')
            result = ask(doc_chat, 'What budget does this document specify? If not supplied, say it is not specified. Cite the filename when relevant.', [file['id']])
            report('PDF missing information', result, bool(re.search(r"not (?:specified|provided|mentioned|stated|supplied)|does not (?:specify|provide|mention|state)|doesn't (?:specify|provide|mention|state)", result['reply'], re.I)) and result['context'].get('citation_check', {}).get('status') != 'invalid')
            if os.environ.get('KENO_EVAL_PDF'):
                real_chat = chat()
                raw = Path(os.environ['KENO_EVAL_PDF']).read_bytes()
                uploaded = call('POST', '/api/v1/attachments', json={'conversation_id': real_chat, 'name': os.environ.get('KENO_EVAL_PDF_NAME', 'user-document.pdf'), 'data_base64': base64.b64encode(raw).decode()})
                result = ask(real_chat, 'Summarize the document with filename/page citations. Separate the document claims from recommendations and identify missing coverage.', [uploaded['id']])
                report('user PDF: manual factual review required', result, True)
                results[-1]['passed'] = False if result.get('evaluation_error') else None

    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

print(json.dumps({'results': results, 'note': 'Menu accuracy and general answer quality still require human review. These checks do not certify factual correctness.'}, indent=2))
raise SystemExit(0 if all(r['passed'] is not False for r in results) else 1)
