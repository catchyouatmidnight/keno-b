"""Real authenticated lab endpoints, backed by an isolated SQLite database."""
import base64
from app import main
from test_backend import client, fake_model, fake_router, new_conversation


def test_lab_auth_snapshot_results_and_reviews(client):
    assert client.get('/api/v1/lab/cases',headers={'Authorization':'Bearer wrong'}).status_code==401
    snap=client.post('/api/v1/lab/snapshots').json()
    assert main.API_KEY not in str(snap)
    case=client.post('/api/v1/lab/cases',json={'title':'Routine','input':'Hello','assertions':[{'kind':'manual'}]}).json()
    main.app.state.llm=fake_model(mode='no_reasoning',chunks=['Hello.'])
    session=new_conversation(client)
    request='lab-request-0001'
    reply=client.post('/api/v1/chat',json={'conversation_id':session,'request_id':request,'message':'Hello'});assert reply.status_code==200,reply.text
    value={'batch_id':'batch-0001','case_id':case['id'],'snapshot_id':snap['id'],'request_id':request,'conversation_id':session,'status':'complete','checks':[{'kind':'manual','passed':None,'detail':'Review'}],'browser_seconds':0}
    wrong=client.post('/api/v1/lab/results',json={**value,'conversation_id':'wrong'});assert wrong.status_code==422
    saved=client.post('/api/v1/lab/results',json=value);assert saved.status_code==201,saved.text
    identifier=saved.json()['id']
    assert client.put('/api/v1/lab/results/'+identifier+'/review',json={'quality':6}).status_code==422
    assert client.put('/api/v1/lab/results/'+identifier+'/review',json={'quality':4,'note':'Human check'}).status_code==200
    client.delete('/api/v1/lab/cases/'+case['id'])
    result=client.get('/api/v1/lab/results').json()['items'][0]
    assert result['case']['input']=='Hello' and result['browser_seconds']==0
    assert result['checks'][0]['passed'] is None and result['review']['quality']==4
    assert result['run']['request_id']==request
    assert client.get('/api/v1/lab/runs').json()['total']==1
    assert client.post('/api/v1/lab/cases',json={'title':'Bad','input':'Hello','secret':'bad'}).status_code==422


def test_encrypted_library_fixture_and_passage_preview(client,monkeypatch):
    monkeypatch.setenv('KENO_DOCUMENT_KEY','ab'*32)
    uploaded=client.post('/api/v1/library/documents',json={'name':'deadline.txt','data_base64':base64.b64encode(b'Deadline: April 2027.').decode(),'embed':False})
    assert uploaded.status_code==200,uploaded.text
    doc=uploaded.json()['id']
    assert client.get('/api/v1/library/documents/'+doc+'/passages/1').json()['text']=='Deadline: April 2027.'
    assert client.get('/api/v1/library/documents/'+doc+'/passages/999').status_code==404
    main.app.state.llm=fake_model(mode='no_reasoning',chunks=['April 2027.'])
    main.app.state.laya=fake_router(family='documents',tool_need='answer')
    response=client.post('/api/v1/chat',json={'conversation_id':new_conversation(client),'request_id':'lab-document-request','message':'When is the deadline?','library_document_ids':[doc]})
    assert response.status_code==200,response.text
    assert response.json()['context']['document_sources'][0]['library_document_id']==doc
    with main.db() as connection:
        assert connection.execute('SELECT count(*) FROM attachments').fetchone()[0]==0
        assert b'Deadline' not in connection.execute('SELECT payload FROM vault_documents').fetchone()[0]
    assert client.get('/api/v1/library/documents/'+doc+'/passages/1',headers={'Authorization':'Bearer wrong'}).status_code==401
