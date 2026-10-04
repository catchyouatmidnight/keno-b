import importlib.util
import httpx
from fastapi.testclient import TestClient


def test_optional_lookup_auth_fixed_destinations_and_bad_provider_payload(monkeypatch):
    spec=importlib.util.spec_from_file_location('lookup_server','lookup-service/server.py')
    lookup=importlib.util.module_from_spec(spec);spec.loader.exec_module(lookup)
    monkeypatch.setattr(lookup,'KEY','x'*40)
    seen=[]
    malformed=False
    def outbound(request):
        seen.append((request.url.host,dict(request.url.params)))
        if malformed:return httpx.Response(200,json=['invalid'])
        if request.url.host=='geocoding-api.open-meteo.com':
            return httpx.Response(200,json={'results':[{'name':'Jakarta','country':'Indonesia','latitude':-6.2,'longitude':106.8}]})
        if request.url.host=='api.open-meteo.com':
            return httpx.Response(200,json={'current':{'temperature_2m':24},'daily':{'temperature_2m_max':[30]}})
        assert request.url.host=='search'
        return httpx.Response(200,json={'results':[{'title':'Result','url':'https://example.org/','content':'<b>Snippet</b>'},{'url':'javascript:alert(1)'}]})
    with TestClient(lookup.app) as client:
        lookup.app.state.http=httpx.AsyncClient(transport=httpx.MockTransport(outbound))
        assert client.post('/weather',json={'city':'Jakarta'}).status_code==401
        client.headers['Authorization']='Bearer '+'x'*40
        assert client.post('/weather',json={'city':'Jakarta'}).json()['location']['name']=='Jakarta'
        assert seen[0]==('geocoding-api.open-meteo.com',{'name':'Jakarta','count':'1','language':'en','format':'json'})
        assert client.post('/search',json={'query':'Linux release'}).json()['results']==[{'title':'Result','url':'https://example.org/','snippet':'Snippet'}]
        assert client.post('/weather',json={'city':'Jakarta','history':'private'}).status_code==422
        malformed=True
        assert client.post('/weather',json={'city':'Jakarta'}).status_code==502
        assert client.post('/search',json={'query':'Linux release'}).status_code==502
