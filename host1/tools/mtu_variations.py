"""New MTU value/order factorial replay against pre-frozen production code."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from knowledge.evidence import ROOT, local_path, read, ref, verify, context, pointer
from reasoning_agent.mtu import run, save
from agent_contract.models import Request, validate_pair

BASE=ROOT/'data/host1/mtu-replay/20261120T143211Z/fixtures'
FAMILIES={'L12':{'wide':(1492,9000),'close':(1500,1501)},
          'L35':{'wide':(1280,9216),'close':(8999,9000)}}

def check_code(directory):
    for path,sha in read(directory/'code-before.json')['production_code'].items():verify(path,sha)

def fixture(folder,link,stage,node_values,reverse,originals):
    folder.mkdir(parents=True,exist_ok=False)
    source=BASE/link/str(stage)/'bundle.json';originals[ref(source)['path']]=ref(source)['sha256']
    bundle=read(source);e=bundle['evidence']
    for entry in e['inputs'].values():
        if isinstance(entry,dict):originals[entry['path']]=entry['sha256']
    graph=read(verify(e['inputs']['graph']['path'],e['inputs']['graph']['sha256']))
    snap=read(verify(e['inputs']['snapshot']['path'],e['inputs']['snapshot']['sha256']))
    inventory=read(verify(e['inputs']['inventory']['path'],e['inputs']['inventory']['sha256']))
    if reverse:next(x for x in inventory['links'] if x['id']==link)['endpoints'].reverse()
    ip=folder/'inventory.json';save(ip,inventory)
    for n in e['interfaces']:
        node=n['router']+':'+n['name'];value=node_values[node]
        target=next(x for x in graph['nodes'] if x['id']==n['id'])
        row=next(x for x in pointer(snap,target['evidence']['pointer'])['data'] if x['name']==n['name'])
        row['mtu']=value;target['observed']['mtu']=value
    sp=folder/'snapshot.json';save(sp,snap);sr=ref(sp)
    graph['graph'].update(snapshot=sr['path'],snapshot_sha256=sr['sha256'],inventory_sha256=ref(ip)['sha256'])
    for item in graph['nodes']+graph['edges']:
        ev=item.get('evidence')
        if isinstance(ev,dict) and 'snapshot' in ev:ev['snapshot']=sr['path']
    gp=folder/'graph.json';save(gp,graph)
    bundle['evidence']=context(gp,ip,link);bp=folder/'bundle.json';save(bp,bundle)
    save(folder/'provenance.json',dict(synthetic=True,collector_measurement=False,source=ref(source),
        node_mtu=node_values,reverse_endpoint_order=reverse,
        meaning='Inventory order reversal only; value swapping is a separate assigned factor. Peer states unchanged.'))
    return ref(bp)

def prepare(directory):
    check_code(directory);cases=[];expected={};originals={};groups={};counter=0
    for link,families in FAMILIES.items():
        base=read(BASE/link/'0/bundle.json')['evidence']
        nodes=[n['router']+':'+n['name'] for n in base['interfaces']]
        for family,(a,b) in families.items():
            for reverse in (False,True):
                for swapped in (False,True):
                    label=f'{link}-{family}-o{int(reverse)}-s{int(swapped)}';samples=[];intent=[]
                    for stage in range(3):
                        values=([b,a] if swapped else [a,b]) if stage==1 else [a,a]
                        node_values=dict(zip(nodes,values));intent.append(node_values)
                        samples.append(fixture(directory/'fixtures'/label/str(stage),link,stage,node_values,reverse,originals))
                    groups[label]=(samples,intent)
                    counter+=1;ident=f'v{counter:02}'
                    seq=directory/'sequences'/(ident+'.json');seq.parent.mkdir(exist_ok=True)
                    save(seq,dict(schema_version='mtu-sequence-1.0',synthetic=True,history_complete=True,snapshots=samples[:2]))
                    cases.append(dict(id=ident,link=link,family=family,reverse=reverse,swapped=swapped,kind='factorial_fault',sequence=ref(seq)))
                    expected[ident]=dict(phase='fault',node_values=intent[:2])
                    if family=='wide' and not swapped:
                        for kind,indices,complete,phase in (
                            ('baseline',[0],True,'baseline'),('recovered',[0,1,2],True,'recovered'),
                            ('partial',[2],False,'undetermined')):
                            counter+=1;cid=f'v{counter:02}';path=seq.parent/(cid+'.json')
                            save(path,dict(schema_version='mtu-sequence-1.0',synthetic=True,history_complete=complete,snapshots=[samples[i] for i in indices]))
                            cases.append(dict(id=cid,link=link,family=family,reverse=reverse,swapped=False,kind=kind,sequence=ref(path)))
                            expected[cid]=dict(phase=phase,node_values=[intent[i] for i in indices])
        for kind,value,reason in (('zero',0,'unknown_or_invalid_mtu'),('overflow',65536,'unknown_or_invalid_mtu'),
                                  ('string','1492','unknown_or_invalid_mtu'),('bundle_tamper',1492,'Bundle differs')):
            values=dict(zip(nodes,[value,9000]));folder=directory/'fixtures'/(link+'-'+kind)
            bp=fixture(folder,link,1,values,True,originals)
            if kind=='bundle_tamper':
                bundle=read(local_path(bp['path']));bundle['evidence']['interfaces'][0]['observed']['mtu']+=7
                save(local_path(bp['path']),bundle);bp=ref(bp['path'])
            counter+=1;ident=f'v{counter:02}';seq=directory/'sequences'/(ident+'.json')
            save(seq,dict(schema_version='mtu-sequence-1.0',synthetic=True,history_complete=True,snapshots=[bp]))
            cases.append(dict(id=ident,link=link,kind=kind,reverse=True,sequence=ref(seq)))
            expected[ident]=dict(phase='abstain',reason=reason)
    random.Random(2026112039).shuffle(cases)
    save(directory/'cases.json',cases);save(directory/'expected.json',expected)
    hashes={ref(p)['path']:ref(p)['sha256'] for parent in ('fixtures','sequences') for p in (directory/parent).rglob('*.json')}
    save(directory/'preregistered.json',dict(at=datetime.now(timezone.utc).isoformat(),
        cases=ref(directory/'cases.json'),expected=ref(directory/'expected.json'),files=hashes,originals=originals,
        harness=ref(Path(__file__)),
        scope='New numeric/order layouts on two known synthetic traces. LLM sees only canonical relations, not numeric values or endpoint IDs.'))
    check_code(directory);print(json.dumps(dict(cases=len(cases),production_unchanged=True)))

def signature(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def resolve_pointer(document,locator):
    result=document
    for raw in locator.lstrip('/').split('/'):
        key=raw.replace('~1','/').replace('~0','~')
        if isinstance(result,list):
            index=int(key)
            if str(index)!=key or not 0<=index<len(result):raise ValueError('Invalid array pointer index')
            result=result[index]
        else:result=result[key]
    return result

def audit_result(path,case,expected):
    audit=read(path/'audit.json');response=read(path/'output-contract.json')
    if response['execution_allowed'] is not False or response['proposed_patch']!=[]:raise ValueError('Unsafe output')
    if expected['phase']=='abstain':
        return dict(passed=audit['status']=='abstain' and not audit['model_called'] and expected['reason'] in audit.get('reason',''),
                    model_called=audit['model_called'],reason=audit.get('reason'))
    req=Request.model_validate(read(path/'input-contract.json'));validate_pair(req.model_dump(),response)
    payload=read(path/'visible-evidence.json');refs={r.id:r for r in req.evidence};bindings=[]
    if len(payload['observations'])!=len(expected['node_values']):raise ValueError('Wrong sample count')
    for obs,wanted in zip(payload['observations'],expected['node_values']):
        if {r['node']:r['mtu'] for r in obs['endpoints']}!=wanted:raise ValueError('Endpoint value mapping changed')
        for row,ident in zip(obs['endpoints'],obs['interface_refs']):
            r=refs[ident];snapshot=read(verify(r.source_path,r.sha256));actual=resolve_pointer(snapshot,r.locator)
            router=r.locator.split('/')[2]
            if row['node']!=router+':'+actual['name'] or row['mtu']!=actual['mtu']:raise ValueError('Citation points to wrong endpoint')
            if json.loads(r.content)!=row:raise ValueError('Citation content differs from selected value')
            statement=f'{obs["time"]}: {row["node"]} MTU={row["mtu"]}, admin UP/carrier UP.'
            claims=[c for c in response['claims'] if c['evidence_ids']==[ident]]
            if audit['status']=='hypothesis' and claims!=[dict(statement=statement,evidence_ids=[ident])]:
                raise ValueError('Numeric claim not supported by own citation')
            bindings.append(dict(id=ident,node=row['node'],mtu=row['mtu'],source=ref(r.source_path),locator=r.locator))
        graph=read(verify(refs[obs['graph_ref']].source_path,refs[obs['graph_ref']].sha256))
        link=case['link'];physical=[x for x in graph['edges'] if x['kind']=='physical' and x.get('link_id')==link]
        if not physical or any(x['state']!='up' for x in physical):raise ValueError('Unexpected physical impact fixture')
    relations=['EQUAL' if len(set(v.values()))==1 else 'UNEQUAL' for v in expected['node_values']]
    model_input=dict(current_relation=relations[-1],earlier_relations=relations[:-1],coverage='complete' if payload['history_complete'] else 'partial')
    if model_input!=read(path/'model-input.json'):raise ValueError('Model input differs from independently scored relation')
    raw=json.loads(read(path/'ollama-response.json')['response'])
    passed=audit.get('contract_valid') is True and raw==dict(phase=expected['phase'])
    if passed:
        if audit.get('routing_impact')!='not_established' or audit.get('root_cause_status')!='not_established':raise ValueError('Unproven causal claim')
        if 'tidak membuktikan gangguan routing' not in response['root_cause_hypothesis']:raise ValueError('Missing impact boundary')
    save(path/'binding-audit.json',dict(bindings=bindings,passed=True,scope='Pointer/numeric claim mapping; not free-prose entailment'))
    return dict(passed=passed,model_called=audit['model_called'],raw_phase=raw,reason=audit.get('reason'),
        input_signature=signature(read(path/'ollama-request.json')),model_input=model_input,bindings=len(bindings))

def evaluate(directory):
    check_code(directory);registered=read(directory/'preregistered.json')
    for entry in (registered['cases'],registered['expected'],registered['harness']):verify(entry['path'],entry['sha256'])
    for path,sha in {**registered['files'],**registered['originals']}.items():verify(path,sha)
    cases=read(directory/'cases.json');expected=read(directory/'expected.json');output=directory/'evaluation';output.mkdir(exist_ok=False)
    rows=[]
    for case in cases:
        check_code(directory);verify(registered['harness']['path'],registered['harness']['sha256'])
        seq=verify(case['sequence']['path'],case['sequence']['sha256'])
        run(seq,output/case['id'])
        result=audit_result(output/case['id'],case,expected[case['id']])
        row=dict(id=case['id'],link=case['link'],kind=case['kind'],reverse=case['reverse'],
            swapped=case.get('swapped'),family=case.get('family'),expected=expected[case['id']]['phase'],**result)
        rows.append(row);print(json.dumps(row),flush=True)
    check_code(directory)
    for path,sha in {**registered['files'],**registered['originals']}.items():verify(path,sha)
    verify(registered['harness']['path'],registered['harness']['sha256'])
    cells=[]
    for reverse in (False,True):
        for swapped in (False,True):
            selected=[r for r in rows if r['kind']=='factorial_fault' and r['reverse']==reverse and r['swapped']==swapped]
            cells.append(dict(reverse=reverse,swapped=swapped,total=len(selected),passed=sum(r['passed'] for r in selected)))
    signatures={}
    for r in rows:
        if r['model_called']:signatures.setdefault(r['input_signature'],[]).append(r['id'])
    save(output/'summary.json',dict(total=len(rows),passed=sum(r['passed'] for r in rows),
        model_calls=sum(r['model_called'] for r in rows),bindings_checked=sum(r.get('bindings',0) for r in rows),
        production_unchanged=True,harness_unchanged=True,fixtures_unchanged=True,originals_unchanged=True,
        factorial=cells,request_signature_groups=signatures,unique_model_requests=len(signatures),cases=rows,
        limitation='Canonicalization removes numeric/order variation before LLM. Tests pipeline binding, not LLM numeric generalization or routing causality.'))
    return 0 if all(r['passed'] for r in rows) else 1

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','evaluate']);p.add_argument('directory');a=p.parse_args()
    if a.action=='prepare':prepare(local_path(a.directory))
    else:raise SystemExit(evaluate(local_path(a.directory)))
