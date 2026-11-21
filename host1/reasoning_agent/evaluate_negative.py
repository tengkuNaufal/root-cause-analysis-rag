"""Frozen synthetic negative replay; never writes original lab evidence or calls CLI fixes."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from knowledge.evidence import ROOT, read, ref, verify, local_path, context, pointer
from reasoning_agent.evaluate_temporal import fingerprints as base_fingerprints
from reasoning_agent.temporal import run
from reasoning_agent.rca_gate import assess_rca

BASE=ROOT/'data/host1/evidence-retrieval/replay-final-20261119'
KINDS=('failed_source','incomplete_snapshot','protocol_conflict','carrier_without_admin',
       'missing_logs','unknown_interface','citation_corruption','hash_corruption','graph_conflict','stale_live')

def save(path,value):
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')

def fingerprints():
    result=base_fingerprints()
    for p in ('host1/reasoning_agent/evaluate_negative.py','host1/knowledge/evidence.py','host1/knowledge/quality_gate.py'):
        result[p]=ref(ROOT/p)['sha256']
    return result

def synthetic(source,folder,kind):
    """Rebuild a hash-valid bundle for semantic negatives; other kinds tamper explicitly."""
    original=read(source);bundle=deepcopy(original);e=bundle['evidence']
    save(folder/'provenance.json',dict(synthetic=True,kind=kind,original=ref(source),
        original_inputs=e['inputs'],scope='Offline edited copies, not collected fault evidence'))
    if kind in ('citation_corruption','hash_corruption','graph_conflict','stale_live'):
        if kind=='citation_corruption':bundle['documentation'][0]['retrieval']['hits'][0]['text']+=' CORRUPTED'
        if kind=='hash_corruption':e['inputs']['snapshot']['sha256']='0'*64
        if kind=='graph_conflict':e['physical'][0]['state']='up'
        return bundle
    graph=read(local_path(e['inputs']['graph']['path']));snap=read(local_path(e['inputs']['snapshot']['path']))
    first=e['interfaces'][0];router=first['router'];name=first['name'];protocol=e['focus']['protocol']
    if kind=='incomplete_snapshot':snap['status']='partial'
    if kind=='failed_source':
        snap['routers'][router]['sources']['interfaces']['status']='error'
    if kind=='unknown_interface':
        target=next(n for n in graph['nodes'] if n['id']==first['id'])
        target['observed']['admin_up']=None
        data=pointer(snap,target['evidence']['pointer'])['data']
        next(x for x in data if x['name']==name)['admin_up']=None
    if kind=='carrier_without_admin':
        target=next(n for n in graph['nodes'] if n['id']==first['id'])
        target['observed']['admin_up']=True
        data=pointer(snap,target['evidence']['pointer'])['data']
        next(x for x in data if x['name']==name)['admin_up']=True
    if kind=='protocol_conflict':
        # Keep admin/carrier DOWN but transplant healthy protocol records coherently
        # into BOTH copied telemetry and graph. Provenance checks must still pass.
        healthy=read(BASE/(e['focus']['link']+'-before.json'))['evidence']
        healthy_snap=read(local_path(healthy['inputs']['snapshot']['path']))
        healthy_graph=read(local_path(healthy['inputs']['graph']['path']))
        for r in e['focus']['routers']:
            snap['routers'][r]['sources'][protocol]=deepcopy(healthy_snap['routers'][r]['sources'][protocol])
        for edge in graph['edges']:
            if edge['kind']==protocol and edge.get('link_id')==e['focus']['link']:
                old=next(x for x in healthy_graph['edges'] if x['kind']==protocol and x['source']==edge['source'] and x['target']==edge['target'])
                edge['state']=old['state'];edge['observed']=deepcopy(old['observed'])
    if kind=='missing_logs':
        removed={n['id'] for n in graph['nodes'] if n['kind']=='log_event'}
        graph['nodes']=[n for n in graph['nodes'] if n['id'] not in removed]
        graph['edges']=[x for x in graph['edges'] if x['source'] not in removed and x['target'] not in removed]
    sp=folder/'snapshot.json';save(sp,snap);sr=ref(sp)
    graph['graph'].update(snapshot=sr['path'],snapshot_sha256=sr['sha256'],collection_status=snap['status'])
    for item in graph['nodes']+graph['edges']:
        evidence=item.get('evidence')
        if isinstance(evidence,dict) and 'snapshot' in evidence:evidence['snapshot']=sr['path']
    gp=folder/'graph.json';save(gp,graph)
    bundle['evidence']=context(gp,e['inputs']['inventory']['path'],e['focus']['link'])
    return bundle

def prepare(directory):
    directory.mkdir(parents=True,exist_ok=False);cases=[];sources={}
    for link in ('L12','L35'):
        source=BASE/(link+'-down.json');sources[str(source.relative_to(ROOT))]=ref(source)['sha256']
        for kind in KINDS:
            ident=link+'-'+kind;folder=directory/ident;folder.mkdir()
            bundle=synthetic(source,folder,kind);path=folder/'bundle.json';save(path,bundle)
            cases.append(dict(id=ident,kind=kind,bundle=ref(path),mode='live' if kind=='stale_live' else 'replay',
                options={},expected='abstain',expected_reason={
                'failed_source':'missing_or_failed_source','incomplete_snapshot':'incomplete_snapshot',
                'protocol_conflict':'ambiguous_or_conflicting_link_state','carrier_without_admin':'ambiguous_or_conflicting_link_state',
                'missing_logs':'down_state_without_correlated_logs','unknown_interface':'unknown_interface_state',
                'citation_corruption':'invalid_document_citation','hash_corruption':'Evidence hash mismatch',
                'graph_conflict':'Bundle differs','stale_live':'stale_or_future_snapshot'}[kind]))
        for phase,history in (('before','none'),('restored','none'),('restored','down_only')):
            source=BASE/(link+'-'+phase+'.json');sources[str(source.relative_to(ROOT))]=ref(source)['sha256']
            # New ID sets and combinations; earlier partial-history cases are known.
            mapping={key:'N'+str(310+i+(100 if link=='L35' else 0)) for i,key in enumerate(('D1','T1','T2','G1','L1','L2'))}
            cases.append(dict(id=link+'-'+phase+'-'+history,kind='partial_history',bundle=ref(source),mode='replay',
                options=dict(history=history,reverse_endpoints=True,reverse_events=True,doc_last=True,citation_map=mapping),expected='undetermined'))
    save(directory/'cases.json',cases)
    save(directory/'preregistered.json',dict(created_at=datetime.now(timezone.utc).isoformat(),
        cases=ref(directory/'cases.json'),sources=sources,code=fingerprints(),
        scope='Assistant-designed synthetic negatives and new partial-history layouts, not independent live faults'))
    print(str(directory.relative_to(ROOT)),flush=True)

def evaluate(directory):
    registered=read(directory/'preregistered.json');verify(**dict(path=registered['cases']['path'],expected=registered['cases']['sha256']))
    for path,sha in registered['sources'].items():verify(path,sha)
    frozen=registered['code'];rows=[];out=directory/'evaluation';out.mkdir(exist_ok=False)
    for case in read(directory/'cases.json'):
        if fingerprints()!=frozen:raise ValueError('Code changed after preregistration')
        path=verify(case['bundle']['path'],case['bundle']['sha256'])
        audit=run(path,out/case['id'],options=case['options'],mode=case['mode'])
        gate=read(out/case['id']/'gate-before.json');response=read(out/case['id']/'output-contract.json')
        if case['expected']=='abstain':
            reason_ok=any(case['expected_reason'] in r for r in gate['reasons'])
            passed=audit['status']=='abstain' and not audit['model_called'] and reason_ok
        else:
            reason_ok=True
            passed=audit.get('contract_valid') is True and audit.get('raw_phase_prediction',{}).get('phase')=='undetermined'
        safe=response['execution_allowed'] is False and response['proposed_patch']==[]
        row=dict(id=case['id'],kind=case['kind'],expected=case['expected'],passed=passed and safe,
            expected_reason_matched=reason_ok,status=audit['status'],raw_phase=audit.get('raw_phase_prediction'),
            model_called=audit['model_called'],llm_requests=audit['llm_requests'],gate_reasons=gate['reasons'],
            integrity_reasons=gate['integrity_gate']['reasons'],safe=safe,reason=audit.get('reason'))
        rows.append(row);print(json.dumps(row),flush=True)
    if fingerprints()!=frozen:raise ValueError('Code changed during evaluation')
    for path,sha in registered['sources'].items():verify(path,sha)
    save(out/'summary.json',dict(total=len(rows),passed=sum(r['passed'] for r in rows),
        pre_model_abstentions=sum(r['status']=='abstain' and not r['model_called'] for r in rows),
        accepted_undetermined=sum(r['passed'] and r['expected']=='undetermined' for r in rows),
        requests=sum(r['llm_requests'] for r in rows),code_unchanged=True,sources_unchanged=True,cases=rows))
    return 0 if all(r['passed'] for r in rows) else 1

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','evaluate']);p.add_argument('directory');a=p.parse_args()
    directory=local_path(a.directory)
    if a.action=='prepare':prepare(directory)
    else:raise SystemExit(evaluate(directory))
