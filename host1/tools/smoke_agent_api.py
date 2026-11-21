"""Exercise the running local API with real Ollama; preserve all HTTP responses."""
import argparse
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from knowledge.evidence import local_path, ref
from reasoning_agent.mtu import save

CASES=[('temporal.l12.baseline','baseline'),('temporal.l12.fault','fault'),
    ('temporal.l12.recovered','recovered'),('temporal.l35.fault','fault'),
    ('mtu.l35.baseline','baseline'),('mtu.l35.fault','fault'),
    ('mtu.l35.recovered','recovered'),('mtu.l35.partial','undetermined'),
    ('mtu.l12.invalid-mtu',None)]

def main(output,port):
    output=local_path(output);output.mkdir(parents=True,exist_ok=False);base='http://127.0.0.1:'+str(port)
    files=('host1/reasoning_agent/api.py','host1/reasoning_agent/replay-scenarios.json','host1/reasoning_agent/temporal.py',
        'host1/reasoning_agent/mtu.py','host1/agent_contract/models.py','host1/ollama_host/inference-profile.json')
    code={p:ref(p)['sha256'] for p in files};save(output/'implementation.json',code)
    def request(path,body=None):
        req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type':'application/json'} if body is not None else {})
        with urllib.request.urlopen(req,timeout=1200) as response:return response.status,json.load(response)
    status,health=request('/health');save(output/'health.json',health);assert status==200
    status,catalog=request('/v1/scenarios');save(output/'scenarios.json',catalog);assert status==200
    rows=[]
    for scenario,phase in CASES:
        for p,sha in code.items():assert ref(p)['sha256']==sha,'Code changed during HTTP smoke'
        started=time.perf_counter();status,value=request('/v1/replays',dict(scenario_id=scenario));elapsed=time.perf_counter()-started
        save(output/(scenario+'.json'),value)
        assert status==201 and value['scenario_id']==scenario and value['phase']==phase
        assert value['mode']=='replay' and value['execution_allowed'] is False and value['proposed_patch']==[]
        assert value['result']['execution_allowed'] is False and value['result']['proposed_patch']==[]
        assert value['timing']['total_seconds']>=value['timing']['agent_seconds']>0
        assert elapsed>=value['timing']['total_seconds']
        if phase is None:
            assert value['status']=='abstain' and value['model']['called'] is False and value['evidence']==[]
        else:assert value['status']=='hypothesis' and value['model']['called'] is True
        refs={e['id']:e for e in value['evidence']}
        fetched=[]
        for evidence in value['evidence']:
            code_http,item=request(evidence['url']);assert code_http==200 and item==evidence
            assert 'source_path' not in item
            fetched.append(item)
        for claim in value['citations']:
            assert claim['evidence_urls']==[refs[e]['url'] for e in claim['evidence_ids']]
        save(output/(scenario+'-evidence.json'),fetched)
        code_http,stored=request('/v1/runs/'+value['run_id']);assert code_http==200 and stored==value
        row=dict(scenario=scenario,passed=True,status=value['status'],phase=phase,
            model_requests=value['model']['requests'],evidence=len(refs),citation_claims=len(value['citations']),
            client_seconds=elapsed,server_seconds=value['timing']['total_seconds'],run_id=value['run_id'])
        rows.append(row);print(json.dumps(row),flush=True)
    for p,sha in code.items():assert ref(p)['sha256']==sha,'Code changed after HTTP smoke'
    save(output/'summary.json',dict(passed=True,cases=rows,total=len(rows),model_requests=sum(r['model_requests'] for r in rows),
        evidence_fetched=sum(r['evidence'] for r in rows),api_bind='127.0.0.1',code_unchanged=True,
        execution_allowed=False,scope='Real HTTP plus real local Ollama on known registered replay scenarios, not live routing or latency benchmark'))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output');p.add_argument('--port',type=int,default=8765)
    a=p.parse_args();main(a.output,a.port)
