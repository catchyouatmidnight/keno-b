import asyncio
import json
import sqlite3

import httpx
import pytest

from app import main, documents, history, tools
from test_backend import client, fake_model, fake_router, new_conversation, send, simple_pdf, upload


def native_model(actions, mode='ok', seen=None, requests=None):
    baseline = fake_model(mode, seen=seen)
    pending = iter(actions)
    def handler(request):
        body = json.loads(request.content) if request.content else {}
        assert all(m['role'] != 'system' for m in body.get('messages', [])[1:]), 'System message must be at the beginning.'
        if requests is not None:
            requests.append((request.url.path, body))
        if request.url.path == '/v1/chat/completions' and not body.get('stream'):
            calls = next(pending, [])
            if isinstance(calls, str):
                return httpx.Response(200, json={'choices': [{'message': {'role': 'assistant', 'content': calls}, 'finish_reason': 'stop'}]})
            return httpx.Response(200, json={'choices': [{'message': {'role': 'assistant', 'tool_calls': [
                {'id': str(i), 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}
                for i, (name, args) in enumerate(calls)]}, 'finish_reason': 'tool_calls' if calls else 'stop'}]})
        return baseline._transport.handle_request(request)
    return httpx.AsyncClient(base_url='http://llm:8080', transport=httpx.MockTransport(handler))


def test_quick_planner_answer_uses_one_inference_and_preserves_replay(client):
    requests = []
    main.app.state.laya = fake_router(family='memory')
    main.app.state.llm = native_model(['No preferences are saved.'], requests=requests)
    conversation = new_conversation(client)
    first = send(client, conversation, message='Explain my saved preferences.').json()
    assert first['reply'] == 'No preferences are saved.'
    assert first['context']['answer_source'] == 'tool_planner'
    assert '_planner_reply' not in first['context']
    assert first['context']['tool_planning_rounds'] == 1
    assert first['context']['agent_call_limit'] == 4
    assert first['context']['tool_execution_seconds'] == 0
    assert sum(path == '/v1/chat/completions' for path, _ in requests) == 1
    assert send(client, conversation, message='Explain my saved preferences.').json()['reply'] == first['reply']
    assert sum(path == '/v1/chat/completions' for path, _ in requests) == 1


def test_planner_reuse_cannot_claim_unsaved_memory_and_honors_deep_thinking(client):
    requests = []
    main.app.state.laya = fake_router(family='memory')
    main.app.state.llm = native_model(['Saved your name Zain.'], requests=requests)
    response = send(client, new_conversation(client), message='Remember that I prefer blue.').json()
    assert response['context']['answer_source'] == 'memory_guard'
    assert "hasn't been saved" in response['reply']
    assert client.get('/api/v1/memories').json() == []
    requests.clear()
    main.app.state.laya = fake_router(family='memory', thinking='deep')
    main.app.state.llm = native_model(['A quick guess.'], requests=requests)
    response = send(client, new_conversation(client), request_id='planner-deep-001', message='Analyze this carefully.').json()
    assert response.get('reply') == 'A quick guess.', response
    payloads = [body for path, body in requests if path == '/v1/chat/completions']
    assert len(payloads) == 1
    assert payloads[0]['chat_template_kwargs']['enable_thinking'] is True
    assert payloads[0]['reasoning_budget_tokens'] == 384
    assert payloads[0]['max_tokens'] == 896
    assert response['context']['answer_source'] == 'tool_planner'
    assert response['context']['hidden_reasoning_seconds'] is None
    requests.clear()
    main.app.state.laya = fake_router(family='memory')
    main.app.state.llm = native_model(['{"name":"Zain"}'], requests=requests)
    response = send(client, new_conversation(client), request_id='planner-json-001', message='Explain my saved preferences.').json()
    assert response['reply'] == 'Hello Zain'
    assert sum(path == '/v1/chat/completions' for path, _ in requests) == 2


def test_native_memory_save_correct_forget_and_idempotent_replay(client):
    conversation = new_conversation(client)
    main.app.state.laya = fake_router(family='memory')
    main.app.state.llm = native_model([[('memory_save', {'key':'user.name', 'quote':"I'm Zain", 'category':'fact'})]])
    first = send(client, conversation, message="I'm Zain").json()
    assert first['context']['memory_changes'] == [{'action':'save', 'key':'user.name'}]
    assert client.get('/api/v1/memories').json()[0]['content'] == "I'm Zain"
    assert send(client, conversation, message="I'm Zain").json()['reply'] == first['reply']
    assert len(client.get('/api/v1/conversations/'+conversation).json()['turns']) == 1
    main.app.state.llm = native_model([[('memory_save', {'key':'user.name', 'quote':"I'm Roy", 'category':'fact'})]])
    assert send(client, conversation, request_id='correct-name-001', message="Actually I'm Roy").status_code == 200
    assert len(client.get('/api/v1/memories').json()) == 1
    seen=[]
    main.app.state.laya = fake_router()
    main.app.state.llm = fake_model(seen=seen)
    recalled = send(client, new_conversation(client), request_id='new-chat-name-001', message='What is my name?')
    assert recalled.status_code == 200
    assert recalled.json()['reply'] == 'Your name is Roy.'
    assert "I'm Roy" in "\n".join(m["content"] for m in seen[-1] if isinstance(m["content"], str))
    main.app.state.laya = fake_router(family='memory')
    main.app.state.llm = native_model([[('memory_forget', {'key':'user.name', 'quote':'forget my name'})]])
    assert send(client, conversation, request_id='forget-name-001', message='forget my name').status_code == 200
    assert client.get('/api/v1/memories').json() == []


def test_memory_staging_failed_stream_and_cancel_discard_writes(client):
    # A mixed request still generates an answer after staging memory writes.
    # Memory-only requests now return a deterministic save acknowledgement.
    main.app.state.laya = fake_router(family='multiple')
    action=[('memory_save', {'key':'user.name', 'quote':"I'm Zain", 'category':'fact'})]
    main.app.state.llm = native_model([action], mode='interrupted')
    assert send(client, new_conversation(client), message="I'm Zain").status_code == 502
    assert client.get('/api/v1/memories').json() == []
    conversation=new_conversation(client)
    value=main.ChatInput(conversation_id=conversation,message="I'm Zain",request_id='cancel-memory-001')
    with main.db() as c:
        c.execute('INSERT INTO turns (request_id,conversation_id,user_text,status,created_at) VALUES (?,?,?,?,?)',
                  (value.request_id,conversation,value.message,'running',main.now()))
    main.app.state.llm=native_model([action])
    async def cancel():
        await main.app.state.generation_lock.acquire()
        generator=main.generate(value,[{'role':'system','content':'Assistant'},{'role':'user','content':value.message}],
                                {'available_tools':['memory_save'],'thinking_budget':0})
        assert (await anext(generator))[0]=='tool'
        assert (await anext(generator))[1]['status']=='complete'
        await generator.aclose()
    asyncio.run(cancel())
    assert client.get('/api/v1/memories').json()==[]
    assert not main.app.state.generation_lock.locked()


def test_tools_reject_unquoted_facts_and_respect_automatic_memory_setting(client):
    main.app.state.laya=fake_router(family='memory')
    main.app.state.llm=native_model([[('memory_save', {'key':'user.name','quote':'Invented name','category':'fact'})]])
    failed=send(client,new_conversation(client),message="I'm Zain").json()
    assert failed['context']['tool_calls'][0]['status']=='failed'
    assert client.get('/api/v1/memories').json()==[]
    client.put('/api/v1/tools/settings',json={'automatic_memory':False})
    main.app.state.llm=native_model([[('memory_save', {'key':'user.name','quote':"I'm Zain",'category':'fact'})]])
    result=send(client,new_conversation(client),request_id='memory-disabled-001',message="I'm Zain").json()
    assert 'memory_save' not in result['context']['available_tools']
    assert client.get('/api/v1/memories').json()==[]
    main.app.state.llm=native_model([[('memory_save', {'key':'user.name','quote':"I'm Zain",'category':'fact'})]])
    assert send(client,new_conversation(client),request_id='explicit-save-001',message="Remember I'm Zain").status_code==200
    assert client.get('/api/v1/memories').json()[0]['key']=='user.name'


def test_calculator_executes_decimal_arithmetic_and_rejects_code(client):
    main.app.state.laya=fake_router(family='calculator')
    seen=[]
    main.app.state.llm=native_model([[('calculator',{'expression':'0.1 + 0.2'})]],seen=seen)
    result=send(client,new_conversation(client),message='What is 0.1 + 0.2?').json()
    assert result['context']['tool_calls'][0]['status']=='complete'
    tool_results=[json.loads(m['content']) for m in seen[-1] if m['role']=='tool']
    assert tool_results[0]['result']=='0.3'
    main.app.state.llm=native_model([[('calculator',{'expression':"__import__('os').getcwd()"})]])
    failed=send(client,new_conversation(client),request_id='unsafe-calculator-001').json()
    assert failed['context']['tool_calls'][0]['status']=='failed'


def test_document_overview_covers_last_page_and_source_preview(client):
    main.CONTEXT_SIZE=8192
    conversation=new_conversation(client)
    file=upload(client,conversation,'report.pdf',simple_pdf([f'Page {p} useful finding' for p in range(1,12)])).json()
    main.app.state.laya=fake_router(family='documents',scope='overview')
    requests=[]
    main.app.state.llm=native_model([[('document_overview',{})]],requests=requests)
    result=send(client,conversation,message='Summarize the whole report',attachment_ids=[file['id']]).json()
    assert {s['page'] for s in result['context']['document_sources']}==set(range(1,12))
    assert result['context']['document_answer_mode']=='direct_stream'
    assert result['context']['available_tools']==[]
    assert all(body.get('stream') for path,body in requests if path=='/v1/chat/completions')
    page=client.get(f"/api/v1/attachments/{file['id']}/pages/11")
    assert page.status_code==200 and page.headers['content-type']=='image/jpeg'
    assert client.get(f"/api/v1/attachments/{file['id']}/pages/12").status_code==422
    # Tool execution still rejects foreign attachment IDs even when clear document requests skip Laya.
    value=main.ChatInput(conversation_id=conversation,message='Read this file',request_id='foreign-doc-001')
    session=tools.ToolSession(value,[{**file,'sections':[],'kind':'pdf','pages':11}],{'automatic_memory':True,'weather_enabled':False,'search_enabled':False},main.db,main.now,main.app.state.lookup)
    async def foreign():
        with pytest.raises(tools.ToolValidationError):
            await session.execute('document_read',{'attachment_id':'foreign-file','pages':[1]})
    asyncio.run(foreign())
    assert documents.overview([{'id':'image','name':'scan','kind':'image','pages':1,'sections':[]}])['complete_extracted_text'] is False


def test_history_compaction_retrieval_backup_and_delete(client,tmp_path):
    main.app.state.llm=fake_model()
    conversation=new_conversation(client)
    for index in range(7):
        result=send(client,conversation,request_id=f'history-turn-{index:04}',message='Orchid plan' if index==0 else 'Hi').json()
    assert result['context']['history_turns']<=4
    with main.db() as c:
        recent,single=history.context(c,conversation,'Orchid')
        assert not single['relevant_older_excerpts'], 'A single generic term must not retrieve unrelated older history'
        recent,notes=history.context(c,conversation,'Orchid plan')
    assert len(recent)==4
    assert any('Orchid' in r['user_excerpt'] for r in notes['relevant_older_excerpts'])
    backup=tmp_path/'backup.db';backup.write_bytes(client.get('/api/v1/backup').content)
    with sqlite3.connect(backup) as c:
        assert c.execute('PRAGMA user_version').fetchone()[0]==5
        assert c.execute('SELECT COUNT(*) FROM conversation_summaries').fetchone()[0]==1
    client.delete('/api/v1/conversations/'+conversation)
    with main.db() as c:
        assert c.execute('SELECT COUNT(*) FROM conversation_summaries').fetchone()[0]==0


def test_live_tools_off_by_default_and_only_current_user_input_leaves(client):
    calls=[]
    def lookup(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200,json={'current':{'temperature_2m':24},'sources':[{'title':'Weather','url':'https://open-meteo.com/'}]})
    main.app.state.lookup=httpx.AsyncClient(base_url='http://lookup:8000',transport=httpx.MockTransport(lookup))
    main.app.state.laya=fake_router(family='live')
    main.app.state.llm=fake_model()
    off=send(client,new_conversation(client),message='Weather in Jakarta?').json()
    assert off['context']['available_tools']==[] and calls==[]
    client.put('/api/v1/tools/settings',json={'weather_enabled':True})
    client.put('/api/v1/profile',json={'name':'Private owner','background':'Private background in London'})
    main.app.state.llm=native_model([[('weather',{'city':'Jakarta'})]])
    on=send(client,new_conversation(client),request_id='weather-enabled-001',message='Weather in Jakarta?').json()
    assert calls==[{'city':'Jakarta'}] and on['context']['web_sources']
    main.app.state.llm=native_model([[('weather',{'city':'London'})]])
    rejected=send(client,new_conversation(client),request_id='weather-profile-001',message='Weather today?').json()
    assert rejected['context']['tool_calls'][0]['status']=='failed' and len(calls)==1


def test_tool_loop_is_bounded_and_unknown_function_is_not_executed(client):
    main.app.state.laya=fake_router(family='memory')
    seen=[]
    main.app.state.llm=native_model([[('shell',{'command':'id'})],[('shell',{'command':'id'})],[('memory_search',{'query':''})]],seen=seen)
    response=send(client,new_conversation(client)).json()
    assert len(response['context']['tool_calls'])==2
    assert all(item['status']=='failed' for item in response['context']['tool_calls'])
    assert len([m for m in seen[-1] if m['role']=='tool'])==2


def test_schema_two_upgrade_keeps_profile_memories_and_attachments(client,tmp_path):
    from scripts.database import snapshot,validate
    conversation=new_conversation(client)
    client.put('/api/v1/profile',json={'name':'Owner'})
    client.put('/api/v1/memories/preference',json={'key':'preference','content':'Short answers'})
    file=upload(client,conversation,'notes.txt',b'Existing document').json()
    with main.db() as c:
        # Simulate the actual v2 schema before validating the backup.
        for table in ('memory_history', 'response_feedback', 'conversation_preferences', 'memory_meta', 'conversation_summaries'):
            c.execute(f'DROP TABLE {table}')
        c.execute("DELETE FROM settings WHERE key='tools'")
        c.execute('PRAGMA user_version=2')
    old=tmp_path/'v2.db';snapshot(main.DB_PATH,old);validate(old)
    main.initialize()
    assert client.get('/api/v1/profile').json()['name']=='Owner'
    assert client.get('/api/v1/memories').json()[0]['content']=='Short answers'
    assert client.get('/api/v1/tools/settings').json()=={'automatic_memory':True,'weather_enabled':False,'search_enabled':False}
    assert client.get(f"/api/v1/attachments/{file['id']}/pages/1").json()['text']=='Existing document'


def test_web_search_executes_explicit_requests_and_clarified_followups(client, monkeypatch):
    client.put('/api/v1/tools/settings', json={'search_enabled': True})
    outbound = []
    def lookup(request):
        payload = json.loads(request.content)
        outbound.append((request.url.path, payload))
        results = [{'title': f'Match report {i}', 'url': f'https://example.com/match-{i}',
                    'snippet': ('Indonesia vs Thailand details ' * 30)} for i in range(5)]
        return httpx.Response(200, json={'query': payload['query'], 'results': results,
            'sources': [{'title': row['title'], 'url': row['url']} for row in results],
            'coverage': 'search snippets only'})
    main.app.state.lookup = httpx.AsyncClient(base_url='http://lookup:8000', transport=httpx.MockTransport(lookup))
    router_calls = []
    main.app.state.laya = fake_router(family='none', seen=router_calls)
    monkeypatch.setattr(main.calendar_tools, 'current_clock', lambda: {'date':'2026-10-06','timezone':'Asia/Jakarta'})

    conversation = new_conversation(client)
    calls = []
    main.app.state.llm = fake_model(calls=calls, chunks=['Search results are available.'])
    first = send(client, conversation, request_id='search-clarify-001', message='search from google').json()
    assert first['reply'] == 'What would you like me to search for?'
    assert first['context']['route']['tool_policy'] == 'web_search_needs_query'
    assert outbound == []

    query = 'information about the 2026 Indonesia vs Thailand match.'
    second = send(client, conversation, request_id='search-followup-001', message=query).json()
    assert outbound == [('/search', {'query': query})]
    assert second['context']['route']['tool_policy'] == 'web_search_followup'
    assert second['context']['available_tools'] == ['web_search', 'web_inspect']
    assert second['context']['tool_planning_rounds'] == 0
    assert [item['name'] for item in second['context']['tool_calls']] == ['web_search', 'web_inspect', 'web_inspect']
    assert all(item['status'] == 'complete' for item in second['context']['tool_calls'])
    assert second['context']['retrieval_seconds'] >= 0
    assert second['context']['action_tool_seconds'] == 0
    assert len(second['context']['web_sources']) == 2
    assert second['context']['web_sources'][0]['url'] == 'https://example.com/match-0'
    assert second['context']['route']['call_count'] == 0
    assert second['context']['route']['thinking'] is False
    completions = [body for path, body in calls if path == '/v1/chat/completions']
    assert completions and all(body.get('stream') for body in completions)

    outbound.clear()
    main.app.state.llm = fake_model(calls=calls, chunks=['The final was clarified from current search evidence.'])
    clarified = send(client, conversation, request_id='search-refine-001', message='i mean the final').json()
    refined_query = query + ' i mean the final'
    assert outbound == [('/search', {'query': refined_query})]
    assert clarified['context']['route']['tool_policy'] == 'web_search_followup'
    assert clarified['context']['context_policy'] == 'followup'
    assert clarified['context']['history_turns'] == 1

    outbound.clear()
    main.app.state.llm = fake_model(calls=calls, chunks=['The date correction is grounded in fresh results.'])
    corrected = send(client, conversation, request_id='search-relative-001', message='it was yesterday').json()
    assert outbound == [('/search', {'query': refined_query + ' it was yesterday date 2026-10-05'})]
    assert corrected['context']['route']['tool_policy'] == 'web_search_followup'
    assert corrected['context']['route']['call_count'] == 0
    assert corrected['context']['route']['thinking'] is False
    assert router_calls == []

    outbound.clear()
    direct_calls = []
    main.app.state.llm = fake_model(calls=direct_calls, chunks=['Direct search completed.'])
    direct = send(client, new_conversation(client), request_id='search-direct-001',
                  message='Search the web for Keno-B release notes.').json()
    assert outbound == [('/search', {'query': 'Keno-B release notes'})]
    assert direct['context']['route']['tool_policy'] == 'explicit_web_search'
    assert direct['context']['tool_planning_mode'] == 'explicit_web_search'
    assert [item['name'] for item in direct['context']['agent_steps']] == ['web_search', 'web_inspect', 'web_inspect']
    assert all(body.get('stream') for path, body in direct_calls if path == '/v1/chat/completions')


def test_web_search_disabled_never_claims_it_searched(client):
    outbound = []
    main.app.state.lookup = httpx.AsyncClient(base_url='http://lookup:8000',
        transport=httpx.MockTransport(lambda request: outbound.append(request) or httpx.Response(500)))
    main.app.state.laya = fake_router(family='none')
    calls = []
    main.app.state.llm = fake_model(calls=calls)
    result = send(client, new_conversation(client), request_id='search-disabled-001',
                  message='Search the web for the latest Keno-B news.').json()
    assert result['reply'] == 'Web search is off. Enable Search in Tools, then tell me what to look up.'
    assert result['context']['answer_source'] == 'web_search_guard'
    assert result['context']['available_tools'] == []
    assert outbound == []
    assert not any(path == '/v1/chat/completions' for path, _ in calls)


def test_weather_disabled_never_generates_fabricated_conditions(client):
    main.app.state.laya=fake_router(family='none')
    calls=[]
    main.app.state.llm=fake_model(calls=calls)
    response=send(client,new_conversation(client),message='whats the weather today').json()
    assert response['reply']=='Weather lookups are off. Enable Weather in Tools, then tell me which city to check.'
    assert response['context']['answer_source']=='weather_guard'
    assert not any(path=='/v1/chat/completions' for path,_ in calls)
    assert 'New York' not in response['reply']


def test_weather_missing_city_or_invented_tool_city_asks_without_live_claim(client):
    client.put('/api/v1/tools/settings',json={'weather_enabled':True})
    main.app.state.laya=fake_router(family='live')
    outbound=[]
    def lookup(request):
        outbound.append(request)
        raise AssertionError('An invented city must never leave the server')
    main.app.state.lookup=httpx.AsyncClient(base_url='http://lookup:8000',transport=httpx.MockTransport(lookup))
    for index,actions in enumerate(([],[[('weather',{'city':'New York'})]])):
        main.app.state.llm=native_model(actions)
        reply=send(client,new_conversation(client),request_id=f'weather-no-city-{index}',message='whats the weather today').json()
        assert reply['reply']=="Which city should I check? I haven't retrieved any weather data yet."
        assert reply['context']['answer_source']=='weather_guard'
    assert outbound==[]


def test_weather_success_uses_returned_data_and_outage_is_honest(client):
    client.put('/api/v1/tools/settings',json={'weather_enabled':True})
    main.app.state.laya=fake_router(family='live')
    unavailable=False
    def lookup(request):
        if unavailable: return httpx.Response(502,json={'detail':'Provider down'})
        return httpx.Response(200,json={'provider':'Open-Meteo','location':{'name':'Jakarta','country':'Indonesia'},
            'current':{'temperature_2m':27.5,'apparent_temperature':30,'time':'2026-10-04T15:00'},
            'current_units':{'temperature_2m':'°C','apparent_temperature':'°C'},'timezone':'Asia/Jakarta',
            'sources':[{'title':'Open-Meteo','url':'https://open-meteo.com/'}]})
    main.app.state.lookup=httpx.AsyncClient(base_url='http://lookup:8000',transport=httpx.MockTransport(lookup))
    main.app.state.llm=native_model([[('weather',{'city':'Jakarta'})]])
    good=send(client,new_conversation(client),message='Weather in Jakarta today?').json()
    assert good['reply'].startswith('Jakarta, Indonesia: 27.5°C, feels like 30°C.')
    assert 'Asia/Jakarta' in good['reply'] and 'Sunny' not in good['reply']
    assert good['context']['answer_source']=='weather_tool' and good['context']['web_sources']
    unavailable=True
    main.app.state.llm=native_model([[('weather',{'city':'Jakarta'})]])
    bad=send(client,new_conversation(client),request_id='weather-down-001',message='Weather in Jakarta today?').json()
    assert bad['reply'].startswith("I couldn't retrieve weather for Jakarta.")
    assert bad['context']['answer_source']=='weather_guard'
    main.app.state.laya=fake_router(family='none')
    main.app.state.llm=fake_model()
    conceptual=send(client,new_conversation(client),request_id='weather-concept-001',message='Explain how weather forecasting works').json()
    assert conceptual['reply']=='Hello Zain' and 'answer_source' not in conceptual['context']


def test_followup_save_uses_recent_user_fact_and_survives_new_chat(client):
    conversation=new_conversation(client)
    main.app.state.laya=fake_router(family='none')
    main.app.state.llm=fake_model()
    assert send(client,conversation,message='hello im zain, your creator').status_code==200
    capability=send(client,conversation,request_id='capability-001',message='can u remember me for any chats?').json()
    assert 'persist across chats' in capability['reply'] and 'Automatic memory is enabled' in capability['reply']
    main.app.state.laya=fake_router(family='memory')
    main.app.state.llm=native_model([[('memory_save',{'key':'user.name','quote':'Zain','category':'fact'})]])
    saved=send(client,conversation,request_id='followup-save-001',message='save').json()
    assert saved['reply'].startswith('Saved: zain.') and saved['context']['answer_source']=='memory_guard'
    assert client.get('/api/v1/memories').json()[0]['content']=='zain'
    main.app.state.laya=fake_router(family='none')
    seen=[];main.app.state.llm=fake_model(seen=seen)
    result=send(client,new_conversation(client),request_id='followup-new-chat-001',message='Do you know my name?').json()
    assert 'user.name' in result['context']['memory_keys']
    assert 'zain' in "\n".join(m["content"] for m in seen[-1] if isinstance(m["content"], str))


def test_followup_save_rejects_assistant_only_other_chat_and_no_save_evidence(client):
    foreign=new_conversation(client)
    main.app.state.llm=fake_model()
    send(client,foreign,message='Foreign secret fact')
    for index,(previous,quote) in enumerate((('Hi','Hello Zain'),('Hi','Foreign secret fact'),("Don't remember my name Zain",'Zain'))):
        main.app.state.laya=fake_router(family='none');main.app.state.llm=fake_model()
        conversation=new_conversation(client)
        send(client,conversation,request_id=f'past-evidence-{index}',message=previous)
        main.app.state.laya=fake_router(family='memory')
        main.app.state.llm=native_model([[('memory_save',{'key':'user.name','quote':quote,'category':'fact'})]])
        response=send(client,conversation,request_id=f'rejected-save-{index}',message='save').json()
        assert response['reply'].startswith("I couldn't save a fact.")
        assert "hasn't been saved" in response['reply']
        assert all(t['status']=='failed' for t in response['context']['tool_calls'])
    assert client.get('/api/v1/memories').json()==[]


def test_memory_capability_reports_real_settings_and_identity_prompt(client):
    main.app.state.laya=fake_router(family='none');main.app.state.llm=fake_model()
    client.put('/api/v1/tools/settings',json={'automatic_memory':False})
    response=send(client,new_conversation(client),message='can you remember me in future chats?').json()
    assert 'persist across chats' in response['reply'] and 'Automatic memory is off' in response['reply']
    prompt=main.system_prompt([])
    assert 'The USER is a different person' in prompt
    assert 'Use user evidence for identity; admit when unknown' in prompt
    assert 'only successful saves persist' in main.system_prompt([],available_tools=['memory_save'])
    assert client.get('/api/v1/status').json()['version']=='0.5.0'


def test_memory_quote_accepts_spacing_but_preserves_source_and_rejects_paraphrases(client):
    main.app.state.laya=fake_router(family='memory')
    main.app.state.llm=native_model([[('memory_save',{'key':'user.creator','quote':'the fact that im your creator','category':'fact'})]])
    result=send(client,new_conversation(client),message='the fact that im  your creator').json()
    assert result['context']['tool_calls'][0]['status']=='complete'
    assert result['reply'].startswith('Saved: the fact that im  your creator.')
    assert client.get('/api/v1/memories').json()[0]['content']=='the fact that im  your creator'
    main.app.state.llm=native_model([[('memory_save',{'key':'user.creator','quote':'Zain created Keno','category':'fact'})]])
    bad=send(client,new_conversation(client),request_id='paraphrase-rejected-001',message='the fact that im  your creator').json()
    assert bad['context']['tool_calls'][0]['status']=='failed'
    assert 'Do not invent or paraphrase' in bad['context']['tool_calls'][0]['detail']
    assert client.get('/api/v1/memories').json()[0]['content']=='the fact that im  your creator'


def test_user_name_answer_is_grounded_and_not_assistant_identity(client):
    requests = []
    main.app.state.laya = fake_router(family='memory')
    main.app.state.llm = native_model(['I am Amira.'], requests=requests)
    conversation = new_conversation(client)
    result = send(client, conversation, message='My name is Amira. What is my name?').json()
    assert result['reply'] == 'Your name is Amira.'
    assert result['context']['answer_source'] == 'user_name_guard'
    assert result['context']['tool_planning_rounds'] == 0
    assert result['context']['tool_model_seconds'] == 0
    assert not any(path == '/v1/chat/completions' for path, body in requests)
    assert client.get('/api/v1/memories').json() == []
    main.app.state.laya = fake_router(family='none')
    main.app.state.llm = fake_model()
    followup = send(client, conversation, request_id='name-followup-001', message='What is my name?').json()
    assert followup['reply'] == 'Your name is Amira.'
    fresh = send(client, new_conversation(client), request_id='name-fresh-001', message='What is my name?').json()
    assert fresh['context'].get('answer_source') == 'user_name_guard'
    assert "don't have your name" in fresh['reply']
    client.put('/api/v1/memories/user.name', json={'key':'user.name', 'content':'My name is Budi.'})
    requests.clear()
    main.app.state.laya = fake_router(family='memory', thinking='deep')
    main.app.state.llm = native_model([], requests=requests)
    saved = send(client, new_conversation(client), request_id='name-saved-001', message='What is my name?').json()
    assert saved['reply'] == 'Your name is Budi.'
    assert saved['context']['tool_planning_mode'] == 'user_name_guard'
    assert saved['context']['tool_calls'] == []
    assert not any(path == '/v1/chat/completions' for path, body in requests)
    value = main.ChatInput(conversation_id=conversation, message='What is my name? Also calculate 2+2.', request_id='mixed-name-001')
    assert main.user_name_reply(value, [], []) is None
    value.message = 'My name is Amira. What is my name?'
    assert main.user_name_reply(value, [], [{'name':'untrusted.txt'}]) is None


def test_changing_retrieval_preserves_instruction_and_history_prefix(client):
    main.app.state.laya = fake_router(family='none')
    seen=[];main.app.state.llm = fake_model(seen=seen)
    conversation = new_conversation(client)
    send(client, conversation, message='Hello')
    client.put('/api/v1/memories/preference', json={'key':'preference', 'content':'Prefer short replies', 'pinned':True,'category':'preference'})
    send(client, conversation, request_id='prefix-second-001', message='Tell me more')
    first, second = seen[0], seen[-1]
    assert first[0] == second[0]
    assert second[1]['role'] == 'user' and second[1]['content'] == 'Hello'
    assert second[2]['role'] == 'assistant'
    assert second[3]['role'] == 'user' and 'Prefer short replies' in second[3]['content']
    assert second[3]['content'].startswith('Tell me more')
    assert 'Prefer short replies' not in second[0]['content']


def test_tool_completion_does_not_rewrite_system_prefix(client):
    requests=[]
    main.app.state.laya = fake_router(family='calculator')
    main.app.state.llm = native_model([[('calculator', {'expression':'2+2'})]], requests=requests)
    response = send(client, new_conversation(client), message='What is 2+2?').json()
    assert response['context']['tool_calls'][0]['status'] == 'complete'
    payloads=[body for path,body in requests if path == '/v1/chat/completions']
    assert len(payloads) == 2
    assert payloads[0]['messages'][0] == payloads[1]['messages'][0]
    assert payloads[1]['messages'][-1]['role'] == 'tool'
    assert all(m['role'] != 'system' for m in payloads[1]['messages'][1:])


def test_explicit_save_requires_validated_tool_and_survives_new_chat(client):
    requests=[]
    main.app.state.laya = fake_router(family='memory')
    client.put('/api/v1/tools/settings', json={'automatic_memory':False})
    main.app.state.llm = native_model([[('memory_save', {'key':'user.project', 'quote':'I work on project Amira', 'category':'fact'})]], requests=requests)
    saved = send(client, new_conversation(client), message='Remember that I work on project Amira.').json()
    assert saved['context']['tool_save_required'] is True
    assert saved['context']['tool_calls'][0]['status'] == 'complete'
    assert saved['reply'].startswith('Saved: I work on project Amira')
    payload = next(body for path,body in requests if path == '/v1/chat/completions')
    assert payload['tool_choice'] == 'required'
    assert [d['function']['name'] for d in payload['tools']] == ['memory_save']
    assert client.get('/api/v1/memories').json()[0]['content'] == 'I work on project Amira'


def test_required_save_preserves_quote_validation_and_other_tool_choices(client):
    requests=[]
    main.app.state.laya = fake_router(family='memory')
    bad = [('memory_save', {'key':'user.name', 'quote':'Invented fact', 'category':'fact'})]
    main.app.state.llm = native_model([bad,bad], requests=requests)
    result = send(client, new_conversation(client), message='Remember that I work on project Amira.').json()
    assert all(event['status'] == 'failed' for event in result['context']['tool_calls'])
    assert client.get('/api/v1/memories').json() == []
    assert "hasn't been saved" in result['reply']
    requests.clear()
    main.app.state.llm = native_model(['No save requested.'], requests=requests)
    result = send(client, new_conversation(client), request_id='forced-no-save-001', message='Remember that my name is Amira, but do not save it.').json()
    payload = next(body for path,body in requests if path == '/v1/chat/completions')
    assert payload['tool_choice'] == 'auto'
    assert result['context']['tool_save_required'] is False
    assert client.get('/api/v1/memories').json() == []


def test_explicit_name_save_skips_inference_corrects_and_replays(client):
    requests=[]
    main.app.state.laya = fake_router(family='memory')
    client.put('/api/v1/tools/settings', json={'automatic_memory':False})
    main.app.state.llm = native_model([], requests=requests)
    conversation = new_conversation(client)
    saved = send(client, conversation, message='Remember that my name is Zain.').json()
    assert saved['context']['tool_planning_mode'] == 'explicit_name_save'
    assert saved['context']['tool_planning_rounds'] == 0
    assert saved['context']['tool_model_seconds'] == 0
    assert saved['context']['memory_changes'] == [{'action':'save', 'key':'user.name'}]
    assert saved['context']['tool_calls'] == [{'name':'memory_save', 'status':'complete', 'index':1, 'memory_key':'user.name'}]
    assert saved['reply'].startswith('Saved: my name is Zain.')
    assert not any(path == '/v1/chat/completions' for path,body in requests)
    assert send(client, conversation, message='Remember that my name is Zain.').json()['reply'] == saved['reply']
    changed = send(client, conversation, request_id='direct-name-correction', message='Save my name is Amira.').json()
    assert changed['context']['tool_planning_rounds'] == 0
    assert len(client.get('/api/v1/memories').json()) == 1
    main.app.state.laya = fake_router(family='none')
    recalled = send(client, new_conversation(client), request_id='direct-name-recall', message='What is my name?').json()
    assert recalled['reply'] == 'Your name is Amira.'
    assert not any(path == '/v1/chat/completions' for path,body in requests)


def test_explicit_name_parser_leaves_ambiguous_and_negated_requests_to_planner():
    from app.tools import explicit_name_save
    for text in ['My name is Zain.', 'Remember my name is Zain and analyze this',
                 'Remember my name is Zain, then calculate 2+2',
                 'Remember my name is Zain but do not save it.',
                 'Remember my name is 123', 'save', 'Remember that my project is Keno.']:
        assert explicit_name_save(text) is None
    assert explicit_name_save('Please remember that my name is Anne-Marie O’Neill.') == {
        'key':'user.name', 'quote':'my name is Anne-Marie O’Neill', 'category':'fact'}


def test_answer_only_gate_skips_false_multiple_planner_and_streams(client):
    requests=[]
    main.app.state.laya = fake_router(family='multiple', tool_need='answer')
    main.app.state.llm = native_model([], requests=requests)
    response = client.post('/api/v1/chat', json={
        'conversation_id':new_conversation(client), 'request_id':'advice-gate-001',
        'message':'how can i change theme in samsung a36 device', 'max_tokens':512, 'stream':True})
    assert response.status_code == 200
    assert 'event: delta' in response.text and 'event: done' in response.text
    with main.db() as connection:
        raw = connection.execute("SELECT metadata FROM turns WHERE request_id='advice-gate-001'").fetchone()[0]
    metadata=json.loads(raw)
    assert 'tool_family' not in metadata['route']['decisions']
    assert metadata['route']['question_count'] == 2
    assert metadata['route']['call_count'] == 1
    assert metadata['route']['tool_family'] == 'none'
    assert metadata['route']['tool_policy'] == 'answer_only'
    assert metadata['available_tools'] == []
    assert 'tool_planning_rounds' not in metadata
    payloads=[body for path,body in requests if path == '/v1/chat/completions']
    assert len(payloads) == 1 and payloads[0]['stream'] is True
    assert 'tools' not in payloads[0]
    assert 'No repeated question, stock opening, closing, or unrelated personal facts' in payloads[0]['messages'][0]['content']
    assert 'Answer the current request directly' in payloads[0]['messages'][0]['content']


def test_action_gate_keeps_calculator_available(client):
    routed=[]
    main.app.state.laya = fake_router(family='calculator', tool_need='action', seen=routed)
    main.app.state.llm = native_model([[('calculator', {'expression':'17*23'})]])
    response = send(client, new_conversation(client), message='Calculate 17 times 23').json()
    assert response['context']['route']['tool_policy'] == 'action_route'
    assert response['context']['route']['question_count'] == 3
    assert response['context']['route']['call_count'] == 2
    assert [list(body['questions']) for body in routed] == [['thinking', 'tool_need'], ['tool_family']]
    assert response['context']['tool_calls'][0]['status'] == 'complete'
    main.app.state.laya = fake_router(family='invalid', tool_need='action')
    invalid = send(client, new_conversation(client), request_id='invalid-family-stage', message='Calculate 2+2')
    assert invalid.status_code == 200
    assert invalid.json()['reply'] == '2+2 = 4.'
    assert invalid.json()['context']['route']['engine'] == 'deterministic'
    assert invalid.json()['context']['route']['call_count'] == 0
    assert not main.app.state.generation_lock.locked()


def test_name_is_relevant_only_and_bad_preamble_not_replayed(client):
    main.app.state.laya = fake_router(family='none')
    client.put('/api/v1/memories/user.name', json={'key':'user.name', 'content':'my name is Zain', 'pinned':True})
    seen=[]
    main.app.state.llm = native_model(['Your name is Zain. Old device advice.'], seen=seen)
    # Seed the old response as it existed before this fix, without modifying it.
    conversation=new_conversation(client)
    with main.db() as connection:
        connection.execute('INSERT INTO turns (request_id,conversation_id,user_text,assistant_text,status,metadata,created_at) VALUES (?,?,?,?,?,?,?)',
                           ('old-preamble-001',conversation,'how can i change theme in samsung a36 device',
                            'Your name is Zain. Old device advice.','complete','{}',main.now()))
    response=send(client,conversation,message='how can i change theme in samsung a36 device').json()
    assert 'user.name' not in response['context']['memory_keys']
    messages=seen[-1]
    assert messages[2]['content'] == 'Old device advice.'
    assert 'Your name is' not in messages[0]['content']
    assert 'my name is Zain' not in messages[-1]['content']
    with main.db() as connection:
        assert connection.execute("SELECT assistant_text FROM turns WHERE request_id='old-preamble-001'").fetchone()[0] == 'Your name is Zain. Old device advice.'
    assert client.get('/api/v1/memories').json()[0]['content'] == 'my name is Zain'
    recalled=send(client,new_conversation(client),request_id='relevance-recall-001',message='What is my name?').json()
    assert recalled['reply'] == 'Your name is Zain.'
    assert main.history_answer_for_prompt('What is my name?', 'Your name is Zain. You told me earlier.') == 'Your name is Zain. You told me earlier.'


def test_firsthand_save_required_even_when_router_says_answer(client):
    requests = []
    main.app.state.laya = fake_router(family='none')
    main.app.state.llm = native_model([[('memory_save', {'key': 'user.marker', 'quote': 'my evaluation marker is sample123', 'category': 'fact'})]], requests=requests)
    result = send(client, new_conversation(client), message='Remember that my evaluation marker is sample123.').json()
    assert result['context']['route']['tool_policy'] == 'explicit_memory_command'
    assert result['context']['memory_changes'] == [{'action': 'save', 'key': 'user.fact.evaluation_marker'}]
    assert not any(path == '/v1/chat/completions' for path, _ in requests)
    assert 'sample123' in client.get('/api/v1/memories').json()[0]['content']


def test_explicit_field_save_correct_recall_followup_no_inference(client):
    main.app.state.laya = fake_router(family='none')
    requests = []
    main.app.state.llm = native_model([], requests=requests)
    cid = new_conversation(client)
    saved = send(client, cid, message='Remember that my evaluation marker is sample123.').json()
    assert saved['context']['tool_planning_mode'] == 'explicit_field_save'
    assert saved['context']['tool_planning_rounds'] == 0
    assert client.get('/api/v1/memories').json()[0]['content'] == 'my evaluation marker is sample123'
    new = new_conversation(client)
    assert send(client, new, request_id='field-recall', message='What is my evaluation marker?').json()['reply'] == 'Your evaluation marker is sample123.'
    send(client, cid, request_id='field-correction', message='Remember that my evaluation marker is updated456.')
    assert len(client.get('/api/v1/memories').json()) == 1
    assert send(client, new_conversation(client), request_id='field-corrected-recall', message='What is my evaluation marker?').json()['reply'] == 'Your evaluation marker is updated456.'
    assert not any(path == '/v1/chat/completions' for path, _ in requests)


def test_explicit_calculation_executes_without_model_even_on_answer_route(client):
    main.app.state.laya = fake_router(family='none')
    requests = []
    main.app.state.llm = native_model([], requests=requests)
    result = send(client, new_conversation(client), message='Calculate 17 × 23').json()
    assert result['reply'] == '17 * 23 = 391.'
    assert result['context']['answer_source'] == 'calculator_tool'
    assert result['context']['tool_calls'][0]['name'] == 'calculator'
    assert result['context']['tool_calls'][0]['status'] == 'complete'
    assert result['context']['tool_planning_rounds'] == 0
    assert not any(path == '/v1/chat/completions' for path, _ in requests)


def test_direct_field_parser_does_not_consume_mixed_or_untrusted_text():
    from app import tools
    for text in ['Remember that my project is Keno and calculate 2+2.', 'Remember that my project is Keno. Explain it.', 'Do not remember that my project is Keno.', 'Remember that my name is Zain.', 'Remember that my project is   .']:
        assert tools.explicit_field_save(text) is None
    assert tools.explicit_calculation("Calculate __import__('os').getcwd()") is None


def test_natural_location_correction_forget_and_disabled_memory(client):
    main.app.state.laya = fake_router(family='none')
    requests=[]
    main.app.state.llm = native_model([], requests=requests)
    cid=new_conversation(client)
    send(client, cid, message='I live in Bekasi.')
    result=send(client, new_conversation(client), request_id='natural-recall', message='Where do I live?').json()
    assert result['reply'] == 'You live in Bekasi.'
    corrected=send(client, cid, request_id='natural-correct', message='Actually, I moved to Bandung.').json()
    assert len(client.get('/api/v1/memories').json()) == 1
    assert corrected['context']['memory_conflicts'] == [{'key':'user.location','resolution':'newer_user_evidence_supersedes_previous'}]
    assert client.get('/api/v1/memory-history/user.location').json()[0]['content'] == 'I live in Bekasi'
    assert send(client, new_conversation(client), request_id='natural-updated', message='What is my city?').json()['reply'] == 'You live in Bandung.'
    forgotten=send(client, cid, request_id='natural-forget', message='Forget my city.').json()
    assert forgotten['reply'] == 'Forgot the saved location.'
    assert client.get('/api/v1/memories').json() == []
    assert client.get('/api/v1/memory-history/user.location').json() == []
    assert 'location saved' in send(client, new_conversation(client), request_id='natural-unknown', message='Where do I live?').json()['reply']
    assert not any(path == '/v1/chat/completions' for path,_ in requests)
    client.put('/api/v1/tools/settings', json={'automatic_memory':False})
    main.app.state.llm = fake_model()
    send(client, cid, request_id='natural-disabled', message='I live in Bekasi.')
    assert client.get('/api/v1/memories').json() == []


def test_followup_expands_using_references_instead_of_fact_guard(client):
    seen=[]
    main.app.state.laya = fake_router(family='none')
    main.app.state.llm = fake_model(seen=seen)
    cid=new_conversation(client)
    send(client, cid, message='Remember that my evaluation marker is sample123.')
    send(client, cid, request_id='expand-recall', message='What is my evaluation marker?')
    main.app.state.laya = fake_router(family='memory')
    main.app.state.llm = fake_model(seen=seen, chunks=['The saved marker is sample123. It was provided by you; no additional purpose was stated.'])
    result=send(client, cid, request_id='expand-details', message='Tell me more.').json()
    assert result['context']['route']['tool_policy'] == 'followup_expansion'
    assert result['context'].get('answer_source') != 'saved_field_guard'
    prompt=json.dumps(seen[-1])
    assert 'followup_subject' in prompt and 'sample123' in prompt
    assert 'It was provided by you' in result['reply']


def test_negative_forget_is_not_executed_by_native_tools(client):
    main.app.state.laya=fake_router(family='memory')
    client.put('/api/v1/memories/user.location', json={'key':'user.location','content':'I live in Bekasi'})
    main.app.state.llm=native_model([[('memory_forget', {'key':'user.location','quote':"Don't forget my city"})]])
    result=send(client,new_conversation(client),message="Don't forget my city").json()
    assert result['context']['tool_calls'][0]['status'] == 'failed'
    assert client.get('/api/v1/memories').json()[0]['key'] == 'user.location'


def test_natural_corrections_are_followups():
    from app import context_policy
    prior = ['timnas indo vs thailand 2026, score']
    assert context_policy.plan('i mean the final', prior)['mode'] == 'followup'
    assert context_policy.plan('it was yesterday', prior)['mode'] == 'followup'
    assert context_policy.plan('the final match', prior)['recent_limit'] == 4



def test_web_result_save_requires_explicit_request_and_tool_evidence(client):
    client.put('/api/v1/tools/settings', json={'search_enabled': True})
    conversation = new_conversation(client)
    value = main.ChatInput(conversation_id=conversation, message='Search the web for launch date and remember the result.',
                           request_id='save-web-result-001')
    session = tools.ToolSession(value, [], {'automatic_memory':True,'weather_enabled':False,'search_enabled':True},
                                main.db, main.now, main.app.state.lookup, {'web_search_query':'launch date'})
    session.research_evidence.append('Launch date: 12 October 2026.')
    async def run():
        saved = await session.execute('memory_save_result', {'key':'research.launch_date','quote':'Launch date: 12 October 2026.'})
        assert saved['category'] == 'temporary'
        with pytest.raises(tools.ToolValidationError):
            await session.execute('memory_save_result', {'key':'research.bad','quote':'Invented result'})
    asyncio.run(run())
    with main.db() as connection:
        session.commit(connection)
    stored = client.get('/api/v1/memories?q=launch').json()
    assert any(item['key']=='research.launch_date' and item['category']=='temporary' for item in stored)


def test_response_style_memory_is_deterministic_and_persists_across_topics(client):
    text='I need you to remember this, everytime u response. end your sentence with "Sir"'
    natural=tools.natural_memory(text, {'automatic_memory':True})
    assert natural == ('memory_save', {'key':'user.preference.response_style','quote':text,'category':'preference'})
    main.app.state.laya=fake_router(family='memory')
    first=send(client,new_conversation(client),request_id='style-save-001',message=text).json()
    assert first['context']['answer_source']=='memory_guard'
    saved=client.get('/api/v1/memories').json()
    assert saved[0]['key']=='user.preference.response_style'
    seen=[]
    main.app.state.laya=fake_router(family='none')
    main.app.state.llm=fake_model(seen=seen,chunks=['Boil for about 7 minutes, Sir.'])
    second=send(client,new_conversation(client),request_id='style-recall-001',message='how long does it take to boil an egg').json()
    assert 'user.preference.response_style' in second['context']['memory_keys']
    assert second['context']['memory_retrieval'][0]['reason']=='persistent preference'
    system=seen[-1][0]['content']
    assert 'Persistent USER preferences follow' in system
    assert text in system
