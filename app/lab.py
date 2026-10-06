"""Authenticated lab records. Conversation content remains in the existing DB."""
import hashlib
import json
import uuid
from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix='/api/v1/lab', tags=['Keno-B Lab'])
def main():
    from . import main as module
    return module

def initialize():
    with main().db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS lab_cases(id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS lab_snapshots(id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS lab_results(id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL);
        ''')

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')
class Assertion(Strict):
    kind: Literal['contains','excludes','json','sources','tool_family','thinking','max_first_token','max_total','manual','ordered_list']
    value: str = Field(default='', max_length=1000)
class Case(Strict):
    title: str = Field(min_length=1,max_length=120)
    suite: str = Field(default='Custom',max_length=60)
    input: str = Field(min_length=1,max_length=8000)
    setup: list[str] = Field(default_factory=list,max_length=8)
    attachment_ids: list[str] = Field(default_factory=list,max_length=4)
    library_document_ids: list[str] = Field(default_factory=list,max_length=4)
    conversation_id: str | None = Field(default=None,max_length=36)
    expected: str = Field(default='',max_length=2000)
    assertions: list[Assertion] = Field(default_factory=list,max_length=12)
    timeout: int = Field(default=180,ge=10,le=360)
    tags: list[str] = Field(default_factory=list,max_length=12)
    intent: Literal['fresh','repeat','followup'] = 'fresh'
class Check(Strict):
    kind: str = Field(max_length=60)
    passed: bool | None
    detail: str = Field(max_length=2000)
class Result(Strict):
    batch_id: str = Field(min_length=8,max_length=100)
    case_id: str = Field(max_length=36)
    snapshot_id: str = Field(max_length=36)
    request_id: str | None = Field(default=None,max_length=100)
    conversation_id: str | None = Field(default=None,max_length=36)
    status: Literal['complete','failed','canceled']
    checks: list[Check] = Field(default_factory=list,max_length=12)
    browser_seconds: float | None = Field(default=None,ge=0,le=86400)
    browser_first_token_seconds: float | None = Field(default=None,ge=0,le=86400)
    error: str | None = Field(default=None,max_length=2000)
    repetition: int = Field(default=1,ge=1,le=20)

@router.get('/config')
def config():
    m=main()
    identity=m.setting('identity')
    return {'model':m.LLM_MODEL,'context_size':m.CONTEXT_SIZE,'vision_enabled':m.VISION_ENABLED,
            'version':m.VERSION,'router':'laya','max_concurrency':1,'queue_supported':False,
            'prompt_identity_sha256':hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),
            'tools':m.setting('tools'),'timing_note':'Durations overlap; first-delta latency includes prompt processing and possible waiting, not an isolated prompt-eval measurement.'}

@router.post('/snapshots')
def snapshot():
    initialize();identifier=str(uuid.uuid4());created=main().now();payload=config()
    with main().db() as c:c.execute('INSERT INTO lab_snapshots VALUES (?,?,?)',(identifier,json.dumps(payload),created))
    return {'id':identifier,'created_at':created,'configuration':payload}

@router.get('/runs')
def runs(limit:int=Query(default=100,ge=1,le=250),offset:int=Query(default=0,ge=0),status:str|None=None):
    if status not in {None,'complete','failed','running'}:raise HTTPException(422,'Invalid run status')
    with main().db() as c:
        where='WHERE t.status=?' if status else ''
        args=[status] if status else []
        total=c.execute('SELECT count(*) FROM turns t '+where,args).fetchone()[0]
        rows=c.execute('SELECT t.*,c.title AS session_title FROM turns t JOIN conversations c ON c.id=t.conversation_id '+where+' ORDER BY t.rowid DESC LIMIT ? OFFSET ?',[*args,limit,offset]).fetchall()
    return {'total':total,'items':[{**dict(r),'context':json.loads(r['metadata'])} for r in rows]}

@router.get('/cases')
def cases():
    initialize()
    with main().db() as c:return [{'id':r['id'],'created_at':r['created_at'],**json.loads(r['payload'])} for r in c.execute('SELECT * FROM lab_cases ORDER BY created_at DESC')]

@router.post('/cases',status_code=201)
def save_case(value:Case):
    initialize();identifier=str(uuid.uuid4());created=main().now()
    with main().db() as c:
        if c.execute('SELECT count(*) FROM lab_cases').fetchone()[0]>=200:raise HTTPException(422,'Lab limit: 200 cases')
        c.execute('INSERT INTO lab_cases VALUES (?,?,?)',(identifier,value.model_dump_json(),created))
    return {'id':identifier,'created_at':created,**value.model_dump()}

@router.delete('/cases/{identifier}')
def delete_case(identifier:str):
    initialize()
    with main().db() as c:
        if not c.execute('DELETE FROM lab_cases WHERE id=?',(identifier,)).rowcount:raise HTTPException(404,'Case not found')
    return {'deleted':identifier}

@router.get('/results')
def results(limit:int=Query(default=250,ge=1,le=500)):
    initialize()
    with main().db() as c:
        total=c.execute('SELECT count(*) FROM lab_results').fetchone()[0]
        rows=c.execute('SELECT * FROM lab_results ORDER BY created_at DESC LIMIT ?',(limit,)).fetchall()
        items=[]
        for r in rows:
            payload=json.loads(r['payload'])
            snap=c.execute('SELECT payload FROM lab_snapshots WHERE id=?',(payload['snapshot_id'],)).fetchone()
            case=c.execute('SELECT payload FROM lab_cases WHERE id=?',(payload['case_id'],)).fetchone()
            turn=c.execute('SELECT * FROM turns WHERE request_id=?',(payload['request_id'],)).fetchone() if payload['request_id'] else None
            items.append({'id':r['id'],'created_at':r['created_at'],**payload,'configuration':json.loads(snap[0]) if snap else None,'case':payload.get('case_snapshot') or (json.loads(case[0]) if case else None),'run':{**dict(turn),'context':json.loads(turn['metadata'])} if turn else None})
    return {'total':total,'items':items}

@router.post('/results',status_code=201)
def save_result(value:Result):
    initialize();identifier=str(uuid.uuid4());created=main().now()
    with main().db() as c:
        case=c.execute('SELECT payload FROM lab_cases WHERE id=?',(value.case_id,)).fetchone()
        if not case or not c.execute('SELECT 1 FROM lab_snapshots WHERE id=?',(value.snapshot_id,)).fetchone():raise HTTPException(404,'Case or snapshot not found')
        if value.request_id:
            turn=c.execute('SELECT conversation_id FROM turns WHERE request_id=?',(value.request_id,)).fetchone()
            if not turn or turn[0]!=value.conversation_id:raise HTTPException(422,'Run/session reference does not match')
        if c.execute('SELECT count(*) FROM lab_results').fetchone()[0]>=5000:raise HTTPException(422,'Lab limit: 5,000 results')
        payload={**value.model_dump(),'case_snapshot':json.loads(case[0])}
        c.execute('INSERT INTO lab_results VALUES (?,?,?)',(identifier,json.dumps(payload),created))
    return {'id':identifier,'created_at':created}
