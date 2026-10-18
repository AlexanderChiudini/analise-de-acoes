"""Teste de integração contra servidor local ativo; --live consulta provedores."""
import json
import sys
import urllib.request

BASE = 'http://127.0.0.1:8765'
def get(path):
    with urllib.request.urlopen(BASE+path, timeout=60) as response:
        return json.loads(response.read())
token = get('/api/session')['token']
def post(path, body):
    request = urllib.request.Request(BASE+path, data=json.dumps(body).encode(), headers={'Content-Type':'application/json','X-Session-Token':token})
    with urllib.request.urlopen(request, timeout=70) as response:
        return json.loads(response.read())
assert get('/api/health')['database'] == 'sqlite'
with urllib.request.urlopen(BASE) as response:
    assert 'equitylab' in response.read().decode().lower()
data = {'price':47.99,'dy':3.85,'dps':1.85,'eps':1.49,'bvps':4.49,'growth':5,'ipca':4.9,'desired_yield':8,'safety_margin':15}
result = post('/api/assets/WEGE3/simulate', data)
assert abs(result['analysis']['values']['graham']-12.2692567)<.001
assert result['analysis']['final_signal']=='CARA'
if '--live' in sys.argv:
    result = post('/api/assets/WEGE3/refresh', {})
    print(json.dumps({'ticker':result['ticker'],'data':result['data'],'warnings':result['warnings'],'sources':list(result['sources'])},ensure_ascii=True))
print('HTTP integration OK')
