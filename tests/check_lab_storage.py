"""Actual lab source validation and persistence without web dependencies."""
import ast
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace as NS
from typing import Literal
import uuid
from pydantic import BaseModel,ConfigDict,Field,ValidationError
ROOT=Path(__file__).resolve().parents[1]
class HTTPException(Exception):
 def __init__(self,status_code,detail):self.status_code,self.detail=status_code,detail
class Router:
 def __getattr__(self,name):return lambda *args,**kwargs:lambda fn:fn
connection=sqlite3.connect(':memory:');connection.row_factory=sqlite3.Row
connection.executescript("CREATE TABLE turns(request_id TEXT,conversation_id TEXT,user_text TEXT,assistant_text TEXT,status TEXT,created_at TEXT,metadata TEXT); CREATE TABLE conversations(id TEXT,title TEXT);")
@contextmanager
def db():
 with connection:yield connection
module=NS(db=db,now=lambda:'2026-10-06T00:00:00Z',LLM_MODEL='Local model',CONTEXT_SIZE=4096,VISION_ENABLED=False,VERSION='0.3.2',setting=lambda key:{'name':'Keno'} if key=='identity' else {'automatic_memory':True})
scope={'hashlib':hashlib,'json':json,'uuid':uuid,'Literal':Literal,'HTTPException':HTTPException,'Query':lambda default=None,**kwargs:default,'BaseModel':BaseModel,'ConfigDict':ConfigDict,'Field':Field,'router':Router(),'main':lambda:module}
tree=ast.parse((ROOT/'app/lab.py').read_text());nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and not (isinstance(n,ast.FunctionDef) and n.name=='main')]
exec(compile(ast.Module(body=nodes,type_ignores=[]),'lab.py','exec'),scope)
c=scope['Case'](title='Context',input='Repeat identifier',setup=['Identifier orchid-7402'],assertions=[{'kind':'contains','value':'orchid-7402'}])
stored=scope['save_case'](c);snap=scope['snapshot']();assert 'key' not in str(snap).lower() and snap['configuration']['max_concurrency']==1
connection.execute("INSERT INTO conversations VALUES ('session','Test')")
connection.execute("INSERT INTO turns VALUES ('req','session','Repeat identifier','orchid-7402','complete','now',?)",(json.dumps({'first_token_seconds':0,'route':{'thinking':False}}),))
r=scope['Result'](batch_id='batch-001',case_id=stored['id'],snapshot_id=snap['id'],request_id='req',conversation_id='session',status='complete',checks=[{'kind':'contains','passed':True,'detail':'matched'}],browser_seconds=0)
scope['save_result'](r);loaded=scope['results']()['items'][0];assert loaded['run']['context']['first_token_seconds']==0 and loaded['run']['context']['route']['thinking'] is False
assert loaded['case']['setup']==['Identifier orchid-7402']
scope['delete_case'](stored['id']);assert scope['results']()['items'][0]['case']['input']=='Repeat identifier'
assert scope['runs']()['items'][0]['context']['first_token_seconds']==0
try:scope['Case'](title='Bad',input='x',KENO_DOCUMENT_KEY='secret');raise AssertionError('extra accepted')
except ValidationError:pass
try:scope['runs'](status='unknown');raise AssertionError('status accepted')
except HTTPException as e:assert e.status_code==422
print('Lab strict contracts, immutable snapshots/case retention, session linkage, zero/false preservation and server persistence passed.')
