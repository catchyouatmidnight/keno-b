"""Run actual retrieval/context/generation functions without web dependencies."""
import ast
import asyncio
import json
from pathlib import Path
import re
import sqlite3
import time
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[1]
class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail

def functions(path, names, scope):
    tree = ast.parse((ROOT / path).read_text())
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), scope)
    return NS(**{name: scope[name] for name in names})

scope = {'re': re, 'HTTPException': HTTPException, 'QUERY_STOP_WORDS': set('tell me about the this my more'.split())}
docs = functions('app/documents.py', ['overview', 'retrieve', 'answer_excerpts', 'coverage', 'check_citations'], scope)
file = {'id': 'f', 'name': 'business.pdf', 'kind': 'pdf', 'pages': 11,
        'sections': [{'page': p, 'text': ('Secure onboarding restore credentials.' if p == 9 else 'Unrelated delivery schedule.') * 35} for p in range(1, 12)]}
focused = docs.answer_excerpts([file], 'tell me more about secure onboarding')
assert {c['page'] for c in focused} == {9}
assert sum(len(c['text']) for c in focused) <= 2600
broad = docs.answer_excerpts([file], 'summarize', broad=True)
assert {c['page'] for c in broad} == set(range(1, 12))
assert sum(len(c['text']) for c in broad) <= 4000 and all(c['shortened'] for c in broad)
assert {c['page'] for c in docs.answer_excerpts([file], 'read page 9')} == {9}
try:
    docs.answer_excerpts([file], 'read page 12')
    raise AssertionError('Out-of-range page accepted')
except HTTPException as e:
    assert e.status_code == 422
assert docs.check_citations('business.pdf p.9', focused, [file])['status'] == 'present'
assert docs.check_citations('business.pdf p.2', focused, [file])['status'] == 'invalid'

async def run():
    routing_scope = {'math': __import__('math'), 'time': time, 'HTTPException': HTTPException,
                     'httpx': NS(HTTPError=RuntimeError)}
    tree = ast.parse((ROOT / 'app/routing.py').read_text())
    exec(compile(ast.Module(body=[n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))], type_ignores=[]), 'routing.py', 'exec'), routing_scope)
    class Router:
        def __init__(self, need): self.need = need; self.requests = []
        async def post(self, path, json):
            self.requests.append(json)
            choices = {'thinking': 'quick', 'source': 'text', 'document_scope': 'focused',
                       'tool_need': self.need, 'tool_family': 'multiple'}
            # A broad family classifier would choose multiple for this request.
            answers = {k: {'choice': choices[k], 'answer_confidence': .9} for k in json['questions']}
            return NS(raise_for_status=lambda: None, json=lambda: {'answers': answers})
    descriptor = {**file, 'characters': 11000}
    router = Router('answer')
    route = await routing_scope['decide'](router, 'tell me more about secure onboarding', 'Earlier document summary', [descriptor])
    assert route['tool_family'] == 'none' and route['tool_policy'] == 'document_evidence_answer'
    assert len(router.requests) == 1 and route['question_count'] == 4
    assert not any('tool_family' in r['questions'] for r in router.requests)
    action_router = Router('action')
    action_route = await routing_scope['decide'](action_router, 'Compare this document and search the web for current requirements', '', [descriptor])
    assert action_route['tool_family'] == 'multiple' and action_route['tool_policy'] == 'attachment_action'
    assert len(action_router.requests) == 2 and action_route['question_count'] == 5
    connection = sqlite3.connect(':memory:')
    connection.executescript("CREATE TABLE turns(request_id TEXT,conversation_id TEXT,user_text TEXT,assistant_text TEXT,status TEXT,metadata TEXT); INSERT INTO turns VALUES ('r','c','old topic','old answer','complete','{}');")
    class Client:
        async def post(self, path, json):
            if path == '/apply-template':
                assert json['tools'] == []
                data = {'prompt': str(json['messages'])}
            else:
                data = {'tokens': list(range(500))}
            return NS(raise_for_status=lambda: None, json=lambda: data)
        def stream(self, *args, **kwargs):
            assert kwargs['json']['stream'] is True
            return Response()
    class Response:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def raise_for_status(self): pass
        async def aiter_lines(self):
            for content, finish in [('Secure onboarding ', None), ('uses restore credentials (business.pdf p.9).', 'stop')]:
                yield 'data: ' + json.dumps({'choices': [{'delta': {'content': content}, 'finish_reason': finish}]})
            yield 'data: [DONE]'
    class Filter:
        def __init__(self, *args, **kwargs): self.removed = False; self.closing = NS(removed=False)
        def push(self, text, **kwargs): return text
    class Session:
        weather_results = []
        def __init__(self, *args): pass
        def commit(self, c): pass
    lock = asyncio.Lock()
    await lock.acquire()
    hist = NS(reply_language=lambda *args: None,
              context=lambda *args: ([], {'compact_notes': [], 'relevant_older_excerpts': []}), refresh=lambda *args: None)
    tools = NS(catalog=lambda *args: [{'function': {'name': 'document_search'}}], SPECS={},
               ToolSession=Session, web_search_reply=lambda *args: None,
               weather_reply=lambda *args: None, memory_reply=lambda *args: None)
    app = NS(state=NS(llm=Client(), generation_lock=lock, lookup=None))
    docs.visual_inputs = lambda *args: ([], [])
    ns = {'documents': docs, 'tools': tools, 'setting': lambda *args: {}, 'app': app, 'db': lambda: connection,
          'now': lambda: 'now', 'json': json, 're': re, 'time': time, 'HTTPException': HTTPException,
          'VISION_ENABLED': False, 'THINKING_BUDGET': 384, 'UNCERTAIN_THINKING_BUDGET': 96,
          'IMAGE_TOKEN_LIMIT': 1024, 'CONTEXT_SIZE': 4096, 'LLM_MODEL': 'test', 'history': hist,
          'context_policy': NS(FOLLOWUP=re.compile('tell me more'), is_followup=lambda text: bool(re.search(r'tell me more', text, re.I)),
                               plan=lambda *args: {'mode': 'documents', 'recent_limit': 4, 'older': True}),
          'conversation_memory_enabled': lambda *args: True,
          'execution_limits': lambda value: {'history': 4, 'thinking_budget': None, 'output': min(value.max_tokens, 2048), 'context': 4096},
          'select_memories': lambda *args: [], 'memory_retrieval_metadata': lambda *args: [],
          'system_prompt': lambda *args: 'Use local evidence.',
          'history_answer_for_prompt': lambda user, answer: answer,
          'response_style': NS(ResponseFilter=Filter), 'saved_field_reply': lambda *args: None,
          'user_name_reply': lambda *args: None, 'check_tool_budget': None}
    async def forbidden(*args):
        raise AssertionError('Document answer called model planner')
        yield None
    ns['agent'] = NS(plan=forbidden)
    main = functions('app/main.py', ['fit_context', 'generate'], ns)
    value = NS(message='tell me more about secure onboarding', conversation_id='c', request_id='r', max_tokens=512, execution_mode='balanced')
    # Even a conflicting family label cannot override answer-only necessity.
    route['tool_family'] = 'multiple'
    messages, meta = await main.fit_context(value, route, [file])
    assert meta['available_tools'] == [] and meta['history_turns'] == 0
    assert meta['document_answer_mode'] == 'direct_stream'
    assert meta['route']['tool_policy'] == 'document_evidence_answer'
    assert len(messages) == 2 and 'old topic' not in str(messages)
    assert {s['page'] for s in meta['document_sources']} == {9}
    connection.execute("UPDATE turns SET status='running'")
    generator = main.generate(value, messages, meta, attachments=[file])
    assert (await anext(generator))[0] == 'timing'
    first = await anext(generator)
    assert first == ('delta', {'text': 'Secure onboarding '})
    assert connection.execute('SELECT status FROM turns').fetchone()[0] == 'running'
    events = [event async for event in generator]
    assert events[-1][0] == 'done' and events[-1][1]['context']['citation_check']['status'] == 'present'
    assert connection.execute('SELECT status FROM turns').fetchone()[0] == 'complete'
    assert not lock.locked()
    print('Document necessity gate, conflicting multiple label, mixed actions, focused/broad/page retrieval, citations, planner bypass, partial streaming and final persistence checks passed.')
asyncio.run(run())
