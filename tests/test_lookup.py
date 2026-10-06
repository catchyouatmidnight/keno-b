import importlib.util
import httpx
from fastapi.testclient import TestClient


def test_optional_lookup_auth_fixed_destinations_and_bad_provider_payload(monkeypatch):
    spec=importlib.util.spec_from_file_location('lookup_server','lookup-service/server.py')
    lookup=importlib.util.module_from_spec(spec);spec.loader.exec_module(lookup)
    monkeypatch.setattr(lookup,'KEY','x'*40)
    seen=[]
    malformed=False
    monkeypatch.setattr(lookup,'public_target',lambda url: True)
    def outbound(request):
        seen.append((request.url.host,dict(request.url.params)))
        if malformed:return httpx.Response(200,json=['invalid'])
        if request.url.host=='geocoding-api.open-meteo.com':
            return httpx.Response(200,json={'results':[{'name':'Jakarta','country':'Indonesia','latitude':-6.2,'longitude':106.8}]})
        if request.url.host=='api.open-meteo.com':
            return httpx.Response(200,json={'current':{'temperature_2m':24},'daily':{'temperature_2m_max':[30]}})
        if request.url.host=='example.org':
            return httpx.Response(200,headers={'content-type':'text/html'},text='<article>Linux release happened on 2026-10-05. Score 2-1.</article>')
        assert request.url.host=='search'
        return httpx.Response(200,json={'results':[{'title':'Result','url':'https://example.org/','content':'<b>Snippet</b>'},{'url':'javascript:alert(1)'}]})
    with TestClient(lookup.app) as client:
        lookup.app.state.http=httpx.AsyncClient(transport=httpx.MockTransport(outbound))
        assert client.post('/weather',json={'city':'Jakarta'}).status_code==401
        client.headers['Authorization']='Bearer '+'x'*40
        assert client.post('/weather',json={'city':'Jakarta'}).json()['location']['name']=='Jakarta'
        assert seen[0]==('geocoding-api.open-meteo.com',{'name':'Jakarta','count':'1','language':'en','format':'json'})
        search=client.post('/search',json={'query':'Linux release'}).json()
        assert search['results'][0]['title']=='Result'
        assert search['results'][0]['page']['fetched'] is True
        assert '2026-10-05' in search['results'][0]['page']['facts']['dates']
        assert search['verification']['status']=='reviewed'
        assert client.post('/search',json={'query':'Linux release'}).json()['cache_hit'] is True
        assert client.post('/weather',json={'city':'Jakarta','history':'private'}).status_code==422
        malformed=True
        assert client.post('/weather',json={'city':'Jakarta'}).status_code==502
        assert client.post('/search',json={'query':'different query'}).status_code==502



def test_search_detects_generic_claim_conflict_and_uses_third_source(monkeypatch):
    spec=importlib.util.spec_from_file_location('lookup_server_claims','lookup-service/server.py')
    lookup=importlib.util.module_from_spec(spec);spec.loader.exec_module(lookup)
    monkeypatch.setattr(lookup,'KEY','x'*40)
    monkeypatch.setattr(lookup,'public_target',lambda url: True)
    pages={
        'one.example':'<article>Final attendance: 50000. The final was played in Jakarta.</article>',
        'two.example':'<article>Final attendance: 52000. The final was played in Jakarta.</article>',
        'three.example':'<article>Final attendance: 50000. Official match report.</article>',
    }
    def outbound(request):
        if request.url.host=='search':
            return httpx.Response(200,json={'results':[
                {'title':'Official report','url':'https://one.example/report','content':'attendance final'},
                {'title':'Second report','url':'https://two.example/report','content':'attendance final'},
                {'title':'Third report','url':'https://three.example/report','content':'attendance final'},
            ]})
        return httpx.Response(200,headers={'content-type':'text/html'},text=pages[request.url.host])
    with TestClient(lookup.app) as client:
        lookup.app.state.http=httpx.AsyncClient(transport=httpx.MockTransport(outbound))
        client.headers['Authorization']='Bearer '+'x'*40
        result=client.post('/search',json={'query':'final attendance'}).json()
        assert len(result['results'])==3
        assert result['verification']['status']=='verified_after_conflict'
        assert result['verification']['conflict'] is False
        assert result['verification']['verified_from']==2
        assert result['verification']['resolved_conflicts']
        assert result['results'][0]['page']['facts']['claims']
