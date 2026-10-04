import asyncio
import json
import sqlite3

import httpx

from app import main, documents, history
from test_backend import client, fake_model, fake_router, new_conversation, send, simple_pdf, upload


def native_model(actions, mode='ok', seen=None):
    baseline = fake_model(mode, seen=seen)
    pending = iter(actions)
    def handler(request):
        body = json.loads(request.content) if request.content else {}
        if request.url.path == '/v1/chat/completions' and not body.get('stream'):
            calls = next(pending, [])
            return httpx.Response(200, json={'choices': [{'message': {'role': 'assistant', 'tool_calls': [
                {'id': str(i), 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}
                for i, (name, args) in enumerate(calls)]}, 'finish_reason': 'tool_calls' if calls else 'stop'}]})
        return baseline._transport.handle_request(request)
    return httpx.AsyncClient(base_url='http://llm:8080', transport=httpx.MockTransport(handler))


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
    assert send(client, new_conversation(client), request_id='new-chat-name-001').status_code == 200
    assert "I'm Roy" in seen[-1][0]['content']
    main.app.state.laya = fake_router(family='memory')
    main.app.state.llm = native_model([[('memory_forget', {'key':'user.name', 'quote':'forget my name'})]])
    assert send(client, conversation, request_id='forget-name-001', message='forget my name').status_code == 200
    assert client.get('/api/v1/memories').json() == []


def test_memory_staging_failed_stream_and_cancel_discard_writes(client):
    main.app.state.laya = fake_router(family='memory')
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
    main.app.state.llm=native_model([[('document_overview',{})]])
    result=send(client,conversation,message='Summarize the whole report',attachment_ids=[file['id']]).json()
    assert {s['page'] for s in result['context']['document_sources']}==set(range(1,12))
    page=client.get(f"/api/v1/attachments/{file['id']}/pages/11")
    assert page.status_code==200 and page.headers['content-type']=='image/jpeg'
    assert client.get(f"/api/v1/attachments/{file['id']}/pages/12").status_code==422
    main.app.state.llm=native_model([[('document_read',{'attachment_id':'foreign-file','pages':[1]})]])
    failed=send(client,conversation,request_id='foreign-doc-001',attachment_ids=[file['id']]).json()
    assert failed['context']['tool_calls'][0]['status']=='failed'
    assert documents.overview([{'id':'image','name':'scan','kind':'image','pages':1,'sections':[]}])['complete_extracted_text'] is False


def test_history_compaction_retrieval_backup_and_delete(client,tmp_path):
    main.app.state.llm=fake_model()
    conversation=new_conversation(client)
    for index in range(7):
        result=send(client,conversation,request_id=f'history-turn-{index:04}',message='Orchid plan' if index==0 else 'Hi').json()
    assert result['context']['history_turns']<=4
    with main.db() as c:
        recent,notes=history.context(c,conversation,'Orchid')
    assert len(recent)==4
    assert any('Orchid' in r['user_excerpt'] for r in notes['relevant_older_excerpts'])
    backup=tmp_path/'backup.db';backup.write_bytes(client.get('/api/v1/backup').content)
    with sqlite3.connect(backup) as c:
        assert c.execute('PRAGMA user_version').fetchone()[0]==3
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
        c.execute('DROP TABLE conversation_summaries')
        c.execute("DELETE FROM settings WHERE key='tools'")
        c.execute('PRAGMA user_version=2')
    old=tmp_path/'v2.db';snapshot(main.DB_PATH,old);validate(old)
    main.initialize()
    assert client.get('/api/v1/profile').json()['name']=='Owner'
    assert client.get('/api/v1/memories').json()[0]['content']=='Short answers'
    assert client.get('/api/v1/tools/settings').json()=={'automatic_memory':True,'weather_enabled':False,'search_enabled':False}
    assert client.get(f"/api/v1/attachments/{file['id']}/pages/1").json()['text']=='Existing document'


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
