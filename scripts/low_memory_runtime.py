"""Opt-in serial model residency; no change to model inputs or decoding.

Ollama documents an empty generate request with keep_alive=0 as unload:
https://github.com/ollama/ollama/blob/main/docs/api.md#unload-a-model
Only an already resident, digest-verified configured model is unloaded.
"""
import json,os,time,urllib.request
from urllib.parse import urlsplit
from runtime_observation import mark


def enabled():
    return os.environ.get('FOOTBALL_LOW_MEMORY','0')=='1'


def unload_model(base_url,model,stage):
    """Wait for server residency to end, or fail before loading the next model.

    The empty request performs no inference. /api/ps confirmation is not proof
    that Windows has reclaimed physical pages; external memory samples measure
    that separately. Never enumerate and unload unrelated models.
    """
    parsed=urlsplit(base_url)
    if (parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost','::1')
            or parsed.path or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError('Low-memory unloading requires a loopback Ollama endpoint')
    http=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(path,payload=None):
        body=None if payload is None else json.dumps(payload).encode('utf8')
        req=urllib.request.Request(base_url+path,data=body,headers={'Content-Type':'application/json'})
        with http.open(req,timeout=5) as response:return json.load(response)
    def resident():
        rows=request('/api/ps')['models']
        matches=[r for r in rows if r.get('name')==model['name'] or r.get('model')==model['name']]
        if any(r.get('digest')!=model['digest'] for r in matches):
            raise ValueError('Refusing to unload a changed model tag')
        return bool(matches)
    mark(stage+'_unload_start',model=model['name'])
    loaded=resident()
    if loaded:
        response=request('/api/generate',{'model':model['name'],'prompt':'','stream':False,'keep_alive':0})
        if response.get('done') is not True or response.get('done_reason')!='unload':
            raise RuntimeError('Ollama did not acknowledge model unload')
        deadline=time.monotonic()+10
        while resident():
            if time.monotonic()>=deadline:raise TimeoutError('Model still resident after unload')
            time.sleep(.05)
    mark(stage+'_unload_end',model=model['name'],was_loaded=loaded,resident=False)
