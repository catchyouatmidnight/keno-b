from datetime import datetime, timezone
from app import calendar_tools, main, context_policy
from test_backend import client, fake_model, fake_router, new_conversation, send

CLOCK={'date':'2026-10-06','timezone':'Asia/Jakarta'}


def test_calendar_leap_year_boundaries_and_narrow_matching():
    result=calendar_tools.calculate('how many days left until 2030',clock=CLOCK)
    assert result['days']==1183 and result['target']=='2030-01-01' and result['assumed_year_start']
    assert '1,183 days' in calendar_tools.render(result)
    assert calendar_tools.calculate('days until 2028-03-01',clock={'date':'2028-02-28','timezone':'UTC'})['days']==2
    assert calendar_tools.calculate('days until 2026-10-06',clock=CLOCK)['days']==0
    assert calendar_tools.calculate('days until 2026-10-05',clock=CLOCK)['days']==-1
    assert calendar_tools.calculate('days until 2030-02-30',clock=CLOCK)['error']=='invalid_date'
    assert calendar_tools.calculate('how many days until 0000',clock=CLOCK)['error']=='invalid_date'
    assert calendar_tools.calculate('how many days until 2030 and save my name',clock=CLOCK) is None
    assert calendar_tools.calculate('do that',['Change my wallpaper','days until 2030'],clock=CLOCK) is None
    assert calendar_tools.calculate('do that',['days until 2030'],clock=CLOCK)['days']==1183
    assert calendar_tools.calculate('calculate that',['do that','days until 2030'],clock=CLOCK)['days']==1183
    assert 'hari lagi' in calendar_tools.render(calendar_tools.calculate('berapa hari lagi sampai 2030',clock=CLOCK))


def test_clock_uses_configured_timezone(monkeypatch):
    class FixedDatetime:
        @staticmethod
        def now(zone):return datetime(2026,10,5,20,tzinfo=timezone.utc).astimezone(zone)
    monkeypatch.setattr(calendar_tools,'datetime',FixedDatetime)
    monkeypatch.setenv('KENO_TIMEZONE','Asia/Jakarta')
    assert calendar_tools.current_clock()==CLOCK
    monkeypatch.setenv('KENO_TIMEZONE','UTC')
    assert calendar_tools.current_clock()['date']=='2026-10-05'


def test_countdown_and_followup_are_saved_without_model_generation(client,monkeypatch):
    monkeypatch.setattr(calendar_tools,'current_clock',lambda:CLOCK)
    calls=[];main.app.state.llm=fake_model(calls=calls)
    main.app.state.laya=fake_router(family='multiple',thinking='deep')
    conversation=new_conversation(client)
    first=send(client,conversation,message='how many days left until 2030').json()
    assert first['reply']=='1,183 days until 2030-01-01, counting from 2026-10-06 (Asia/Jakarta).'
    assert first['context']['answer_source']=='local_calendar'
    assert first['context']['route']['thinking'] is False
    assert first['context']['tool_planning_rounds']==0
    second=send(client,conversation,request_id='calendar-followup-0001',message='do that').json()
    assert second['reply']==first['reply']
    assert second['context']['followup_context'] is True
    assert second['context']['calendar_calculation']['source_request']=='how many days left until 2030'
    assert not any(path=='/v1/chat/completions' for path,_ in calls)
    assert client.get('/api/v1/conversations/'+conversation).json()['turns'][-1]['status']=='complete'


def test_general_do_that_keeps_adjacent_context(client):
    seen=[];main.app.state.llm=fake_model(mode='no_reasoning',seen=seen)
    main.app.state.laya=fake_router(family='none')
    conversation=new_conversation(client)
    send(client,conversation,message='Give me a plan for studying Indonesian.')
    result=send(client,conversation,request_id='context-do-that-0001',message='do that').json()
    assert result['context']['context_policy']=='followup' and result['context']['history_turns']==1
    assert seen[-1][1]['content']=='Give me a plan for studying Indonesian.'
    assert 'followup_subject' in seen[-1][-1]['content']
    assert context_policy.plan('do it',[])['mode']=='followup'
