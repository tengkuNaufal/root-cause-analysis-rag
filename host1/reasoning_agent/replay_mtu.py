"""Generate isolated, explicit synthetic MTU fixtures and evaluate a frozen suite."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from knowledge.evidence import ROOT, local_path, read, ref, verify, context, pointer
from reasoning_agent.mtu import save, run, prepare_input, explain
from agent_contract.models import validate_pair

BASE=ROOT/'data/host1/evidence-retrieval/replay-final-20261119'
NEGATIVES=('unknown_mtu','boolean_mtu','missing_endpoint','source_error','admin_down',
    'hash_corrupt','citation_corrupt','reversed_time','cross_link','stale_live')

def code_hashes():
    return {p:ref(ROOT/p)['sha256'] for p in ('host1/reasoning_agent/mtu.py','host1/reasoning_agent/replay_mtu.py',
        'host1/knowledge/evidence.py','host1/knowledge/quality_gate.py','host1/reasoning_agent/temporal.py',
        'host1/agent_contract/models.py','host1/reasoning_agent/adapter.py','host1/ollama_host/inference-profile.json')}

def fixture(folder,link,stage,kind=None):
    folder.mkdir(parents=True,exist_ok=False)
    original=read(BASE/(link+'-before.json'));e=original['evidence']
    graph=read(local_path(e['inputs']['graph']['path']));snap=read(local_path(e['inputs']['snapshot']['path']))
    timing=read(BASE/(link+'-'+('before','down','restored')[stage]+'.json'))['evidence']
    ts=read(local_path(timing['inputs']['snapshot']['path']))
    for key in ('started_at','completed_at'):
        snap[key]=ts[key];graph['graph'][key]=ts[key]
    graph['graph']['correlation'].update(window_start=timing['window']['start'],window_end=timing['window']['end'])
    # Remove unrelated historical DOWN logs: these are MTU fixtures, not admin fault logs.
    removed={n['id'] for n in graph['nodes'] if n['kind']=='log_event'}
    graph['nodes']=[n for n in graph['nodes'] if n['id'] not in removed]
    graph['edges']=[x for x in graph['edges'] if x['source'] not in removed and x['target'] not in removed]
    graph['graph']['log_inputs']=[]
    for i,n in enumerate(e['interfaces']):
        node=next(x for x in graph['nodes'] if x['id']==n['id'])
        row=next(x for x in pointer(snap,node['evidence']['pointer'])['data'] if x['name']==n['name'])
        mtu=1400 if stage==1 and i==0 else 1500
        if kind=='unknown_mtu' and i==0:mtu=None
        if kind=='boolean_mtu' and i==0:mtu=True
        for target in (row,node['observed']):
            target['mtu']=mtu
            if kind=='admin_down' and i==0:target['admin_up']=False
        if kind=='source_error' and i==0:pointer(snap,node['evidence']['pointer'])['status']='error'
    if kind=='admin_down':
        for edge in graph['edges']:
            if edge['kind']=='physical' and edge.get('link_id')==link:edge['state']='down'
    sp=folder/'snapshot.json';save(sp,snap);sr=ref(sp)
    graph['graph'].update(snapshot=sr['path'],snapshot_sha256=sr['sha256'])
    for item in graph['nodes']+graph['edges']:
        ev=item.get('evidence')
        if isinstance(ev,dict) and 'snapshot' in ev:ev['snapshot']=sr['path']
    gp=folder/'graph.json';save(gp,graph)
    bundle=deepcopy(original);bundle['evidence']=context(gp,e['inputs']['inventory']['path'],link)
    if kind=='missing_endpoint':bundle['evidence']['interfaces'].pop()
    if kind=='hash_corrupt':bundle['evidence']['inputs']['snapshot']['sha256']='0'*64
    if kind=='citation_corrupt':bundle['documentation'][0]['retrieval']['hits'][0]['text']+=' CORRUPTED'
    bp=folder/'bundle.json';save(bp,bundle)
    save(folder/'provenance.json',dict(synthetic=True,source=ref(BASE/(link+'-before.json')),
        timestamp_source=ref(BASE/(link+'-'+('before','down','restored')[stage]+'.json')),
        change='Copied UP baseline; synthetic endpoint MTUs 1500/1500 -> 1400/1500 -> 1500/1500; no routing impact simulated.',
        negative=kind,collector_measurement=False))
    return ref(bp)

def prepare(directory):
    directory.mkdir(parents=True,exist_ok=False);samples={};cases=[]
    for link in ('L12','L35'):
        samples[link]=[fixture(directory/'fixtures'/link/str(i),link,i) for i in range(3)]
    for link in ('L12','L35'):
        for phase,count in (('baseline',1),('fault',2),('recovered',3)):
            path=directory/(link+'-'+phase+'.json')
            save(path,dict(schema_version='mtu-sequence-1.0',synthetic=True,history_complete=True,snapshots=samples[link][:count]))
            cases.append(dict(id=link+'-'+phase,sequence=ref(path),expected=phase,mode='replay'))
        path=directory/(link+'-partial.json')
        save(path,dict(schema_version='mtu-sequence-1.0',synthetic=True,history_complete=False,snapshots=[samples[link][-1]]))
        cases.append(dict(id=link+'-partial',sequence=ref(path),expected='undetermined',mode='replay'))
        for kind in NEGATIVES:
            if kind in ('reversed_time','cross_link','stale_live'):
                sequence=([samples[link][1],samples[link][0]] if kind=='reversed_time' else
                    [samples[link][0],samples['L35' if link=='L12' else 'L12'][1]] if kind=='cross_link' else [samples[link][0]])
            else:sequence=[fixture(directory/'fixtures'/link/kind,link,1,kind)]
            path=directory/(link+'-'+kind+'.json')
            save(path,dict(schema_version='mtu-sequence-1.0',synthetic=True,history_complete=True,snapshots=sequence))
            cases.append(dict(id=link+'-'+kind,sequence=ref(path),expected='abstain',mode='live' if kind=='stale_live' else 'replay',
                reason=dict(unknown_mtu='unknown_or_invalid_mtu',boolean_mtu='unknown_or_invalid_mtu',
                    missing_endpoint='Bundle differs',source_error='missing_or_failed_source',admin_down='down_state_without_correlated_logs',
                    hash_corrupt='Evidence hash mismatch',citation_corrupt='invalid_document_citation',
                    reversed_time='duplicate_or_reversed_sample_time',cross_link='cross_link_or_endpoint_history',stale_live='stale_or_future_snapshot')[kind]))
    save(directory/'cases.json',cases)
    # Pin every generated fixture and source input, not just the manifest/labels.
    fixture_hashes={str(p.relative_to(ROOT)):ref(p)['sha256'] for p in (directory/'fixtures').rglob('*.json')}
    originals={str((BASE/(l+'-'+s+'.json')).relative_to(ROOT)):ref(BASE/(l+'-'+s+'.json'))['sha256']
        for l in ('L12','L35') for s in ('before','down','restored')}
    save(directory/'preregistered.json',dict(at=datetime.now(timezone.utc).isoformat(),cases=ref(directory/'cases.json'),
        fixtures=fixture_hashes,originals=originals,code=code_hashes(),scope='Synthetic observed MTU inequality only; no live fault or causal routing impact evidence'))
    print(str(directory.relative_to(ROOT)))

def evaluate(directory):
    frozen=read(directory/'preregistered.json');verify(frozen['cases']['path'],frozen['cases']['sha256'])
    for path,sha in {**frozen['fixtures'],**frozen['originals']}.items():verify(path,sha)
    output=directory/'evaluation';output.mkdir(exist_ok=False);rows=[]
    for case in read(directory/'cases.json'):
        if code_hashes()!=frozen['code']:raise ValueError('Code changed after preregistration')
        path=verify(case['sequence']['path'],case['sequence']['sha256'])
        audit=run(path,output/case['id'],case['mode']);response=read(output/case['id']/'output-contract.json')
        if case['expected']=='abstain':
            passed=audit['status']=='abstain' and not audit['model_called'] and case['reason'] in audit.get('reason','')
        else:
            req,payload,_=prepare_input(path)
            validate_pair(req.model_dump(),response)
            passed=audit.get('phase')==case['expected'] and audit.get('contract_valid') is True
            # Independent saved artifacts/raw phase, then exact bounded claim alignment.
            raw=json.loads(read(output/case['id']/'ollama-response.json')['response'])
            passed=passed and raw==dict(phase=case['expected']) and response==explain(req,payload,case['expected'])
        safe=response['execution_allowed'] is False and response['proposed_patch']==[]
        row=dict(id=case['id'],expected=case['expected'],passed=passed and safe,status=audit['status'],
            phase=audit.get('raw_phase'),model_called=audit['model_called'],reason=audit.get('reason'),safe=safe)
        rows.append(row);print(json.dumps(row),flush=True)
    for path,sha in {**frozen['fixtures'],**frozen['originals']}.items():verify(path,sha)
    if code_hashes()!=frozen['code']:raise ValueError('Code changed during evaluation')
    save(output/'summary.json',dict(total=len(rows),passed=sum(r['passed'] for r in rows),
        model_calls=sum(r['model_called'] for r in rows),code_and_sources_unchanged=True,cases=rows))
    return 0 if all(r['passed'] for r in rows) else 1

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','evaluate']);p.add_argument('directory');a=p.parse_args()
    if a.action=='prepare':prepare(local_path(a.directory))
    else:raise SystemExit(evaluate(local_path(a.directory)))
