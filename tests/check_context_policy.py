"""Actual-source context/language checks runnable without the HTTP framework."""
import ast
import json
from pathlib import Path
import re
import sqlite3
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
scope={'re':re,'json':json}
source=ast.parse((ROOT/'app/documents.py').read_text())
stop=next(n for n in source.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='QUERY_STOP_WORDS' for t in n.targets))
exec(compile(ast.Module(body=[stop],type_ignores=[]),'documents.py','exec'),scope)
source=ast.parse((ROOT/'app/context_policy.py').read_text())
exec(compile(ast.Module(body=[n for n in source.body if not isinstance(n,(ast.Import,ast.ImportFrom))],type_ignores=[]),'context_policy.py','exec'),scope)
policy=SimpleNamespace(**{k:scope[k] for k in ['plan','language_choice']})
assert policy.plan('hello',['My name is Zain'])['recent_limit']==0
assert policy.plan('how are u',['Project Orchid budget is 7402'])['older'] is False
assert policy.plan('how long does it take to boil an egg',['My name is Zain'])['recent_limit']==0
assert policy.plan('do that',['Please explain the plan'])['recent_limit']==4
assert policy.plan('repeat that again',['What is my name?'])['recent_limit']==4
assert policy.plan('What is the Orchid budget?',['Project Orchid budget is 7402'])['recent_limit']==2
assert policy.plan('What did we discuss earlier?',[])['older'] is True
assert policy.language_choice('can u speak indonesian') is None
assert policy.language_choice('yea switch','can u speak indonesian')=='Indonesian'
assert policy.language_choice('switch to English')=='English'
assert policy.language_choice('translate "switch to English"') is None
history_scope={'json':json,'re':re,'context_policy':policy,'QUERY_STOP_WORDS':scope['QUERY_STOP_WORDS']}
source=ast.parse((ROOT/'app/history.py').read_text())
exec(compile(ast.Module(body=[n for n in source.body if isinstance(n,(ast.FunctionDef,ast.Assign))],type_ignores=[]),'history.py','exec'),history_scope)
with sqlite3.connect(':memory:') as c:
    c.executescript('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT); CREATE TABLE turns(conversation_id TEXT,user_text TEXT,assistant_text TEXT,status TEXT); CREATE TABLE conversation_summaries(conversation_id TEXT PRIMARY KEY,notes TEXT,updated_at TEXT);')
    for user in ['My name is Zain','can u speak indonesian','yea switch','apa kabar']:
        c.execute('INSERT INTO turns VALUES (?,?,?,?)',('one',user,'Unrelated assistant reply','complete'))
    assert history_scope['reply_language'](c,'one','testing')=='Indonesian'
    assert history_scope['reply_language'](c,'two','hello') is None
    for _ in range(205):c.execute('INSERT INTO turns VALUES (?,?,?,?)',('one','hello','hello','complete'))
    assert history_scope['reply_language'](c,'one','hello')=='Indonesian'
    assert history_scope['reply_language'](c,'one','use English')=='English'
    c.execute('INSERT INTO turns VALUES (?,?,?,?)',('one','use English','Done','complete'))
    history_scope['refresh'](c,'one','test-time')
    assert history_scope['reply_language'](c,'one','hello')=='English'
    recent,older=history_scope['context'](c,'one','hello',0,False)
    assert recent==[] and older=={'compact_notes':[],'relevant_older_excerpts':[]}
    assert len(history_scope['context'](c,'one','repeat that again',4,False)[0])==4
# Prefix remains the same for ordinary messages, memory contents and tool families.
source=ast.parse((ROOT/'app/main.py').read_text())
node=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='system_prompt')
system_scope={'setting':lambda name:{'name':'Keno','personality':'Concise.','response_examples':''}}
exec(compile(ast.Module(body=[node],type_ignores=[]),'main.py','exec'),system_scope)
f=system_scope['system_prompt'];base=f([])
assert len(base)<900 and 'user.name' not in f([{'key':'user.name','content':'Zain'}])
assert f([],available_tools=['calculator'])==f([],available_tools=['memory_save'])
print('Routine/standalone trimming, follow-up relevance, legacy language recovery, durable language choice, isolation and compact stable-prefix checks passed.')
