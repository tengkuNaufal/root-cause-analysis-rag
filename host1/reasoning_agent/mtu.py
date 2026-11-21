"""Read-only MTU inequality profile over verified snapshot sequences, with LLM phase."""
import argparse
import json
from pydantic import BaseModel, ConfigDict
from typing import Literal
from agent_contract.models import Request, Response, validate_pair
from knowledge.evidence import ROOT, local_path, read, verify, ref, instant
from knowledge.quality_gate import assess_context
from reasoning_agent.adapter import Ollama, PROFILE, abstain
from reasoning_agent.temporal import step_request, complete_raw

SYSTEM=('Choose phase from verified MTU observations. Return JSON with phase only. '
    'Examples: '
    'current_relation=UNEQUAL, earlier_relations=[EQUAL], coverage=complete => fault. '
    'current_relation=EQUAL, earlier_relations=[EQUAL,UNEQUAL], coverage=complete => recovered. '
    'current_relation=EQUAL, earlier_relations=[], coverage=complete => baseline. '
    'current_relation=EQUAL, earlier_relations=[], coverage=partial => undetermined. '
    'Current UNEQUAL always means fault. Current EQUAL after any earlier UNEQUAL means recovered. '
    'With only EQUAL observations, complete coverage means baseline and partial coverage means undetermined. '
    'These labels describe observed MTU equality, not proof of a routing failure, repair, actor or cause. '
    'Do not infer a preferred MTU or commands.')

class Phase(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    phase: Literal['baseline','fault','recovered','undetermined']

def save(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')

def definition():
    registry=ROOT/'host1/knowledge/sources-manifest.json'
    entry=next(x for x in read(registry) if x['filename']=='openconfig-openconfig-interfaces.yang')
    path=verify(ROOT/'host1/knowledge/sources'/entry['filename'],entry['sha256']);lines=path.read_text().splitlines()
    a=next(i for i,line in enumerate(lines) if 'leaf mtu {' in line)
    b=next(i for i in range(a+1,a+40) if lines[i].strip()=='}')+1
    return dict(id='D1',kind='documentation',source_path=ref(path)['path'],sha256=entry['sha256'],
        locator=f'{entry["source_url"]}#L{a+1}-L{b}',content='\n'.join(lines[a:b]))

def prepare_input(path,mode='replay'):
    path=local_path(path);manifest=read(path)
    if (manifest.get('schema_version')!='mtu-sequence-1.0' or type(manifest.get('history_complete')) is not bool
        or not isinstance(manifest.get('snapshots'),list) or not 1<=len(manifest['snapshots'])<=3):
        raise ValueError('invalid_sequence_contract')
    refs=[definition()];observations=[];previous=None;identity=None;gates=[]
    for index,entry in enumerate(manifest['snapshots']):
        bundle=read(verify(entry['path'],entry['sha256']));e=bundle['evidence']
        # Earlier samples are historical even when the latest sample must be live-fresh.
        gate=assess_context(bundle,mode=mode if index==len(manifest['snapshots'])-1 else 'replay')
        gates.append(gate)
        reasons=[r for r in gate['reasons'] if r!='no_topically_relevant_verified_documentation']
        if reasons:raise ValueError('source_gate:'+','.join(reasons))
        pair=sorted(n['router']+':'+n['name'] for n in e['interfaces'])
        key=(e['focus']['link'],e['focus']['protocol'],tuple(pair))
        if identity is not None and key!=identity:raise ValueError('cross_link_or_endpoint_history')
        identity=key
        current=instant(e['window']['end'])
        if previous is not None and current<=previous:raise ValueError('duplicate_or_reversed_sample_time')
        previous=current
        if len(pair)!=2 or len(set(pair))!=2:raise ValueError('incomplete_endpoint_pair')
        values=[];ids=[]
        for n in sorted(e['interfaces'],key=lambda n:n['router']+':'+n['name']):
            actual=n['observed']
            if not isinstance(actual,dict) or type(actual.get('mtu')) is not int or not 0<actual['mtu']<65536:
                raise ValueError('unknown_or_invalid_mtu')
            if actual.get('admin_up') is not True or actual.get('lower_up') is not True:
                raise ValueError('admin_or_carrier_confound_outside_mtu_profile')
            node=n['router']+':'+n['name'];ident=f'S{index+1}T{len(values)+1}'
            obs=next(t for t in e['telemetry'] if t['router']==n['router'] and t['source']=='interfaces')
            pos=next(i for i,x in enumerate(obs['observation']['data']) if x['name']==n['name'])
            value=dict(node=node,mtu=actual['mtu'],admin_up=True,carrier_up=True)
            refs.append(dict(id=ident,kind='telemetry',source_path=e['inputs']['snapshot']['path'],
                sha256=e['inputs']['snapshot']['sha256'],locator=f'/routers/{n["router"]}/sources/interfaces/data/{pos}',
                content=json.dumps(value)))
            values.append(value);ids.append(ident)
        if e['physical'][0]['state']!='up':raise ValueError('physical_conflict')
        gid=f'S{index+1}G'
        refs.append(dict(id=gid,kind='graph',source_path=e['inputs']['graph']['path'],sha256=e['inputs']['graph']['sha256'],
            locator='/edges',content=json.dumps(dict(physical='up',peers=[s['state'] for s in e['sessions']]))))
        observations.append(dict(time=e['window']['end'],endpoints=values,interface_refs=ids,graph_ref=gid))
    refs.append(dict(id='H1',kind='graph',source_path=ref(path)['path'],sha256=ref(path)['sha256'],
        locator='/snapshots',content=json.dumps(dict(history_complete=manifest['history_complete'],
            snapshots=manifest['snapshots'],semantics='Controller-supplied ordered history graph; not a collector completeness guarantee'))))
    req=Request(request_id='mtu-'+ref(path)['sha256'][:12],question='Classify observed endpoint MTU equality within the supplied sequence only.',
        mode=mode,snapshot_completed_at=observations[-1]['time'],
        gate=dict(version='mtu-observation-1.0',decision='context_ready',answer_supported=True,reasons=[]),evidence=refs)
    return req,dict(history_complete=manifest['history_complete'],observations=observations),gates

def expected_phase(payload):
    unequal=[x['endpoints'][0]['mtu']!=x['endpoints'][1]['mtu'] for x in payload['observations']]
    if unequal[-1]:return 'fault'
    if any(unequal[:-1]):return 'recovered'
    return 'baseline' if payload['history_complete'] else 'undetermined'

def explain(req,payload,phase):
    # Bounded rendering, not model-authored prose. All numeric facts have endpoint citations.
    claims=[]
    for obs in payload['observations']:
        for row,ident in zip(obs['endpoints'],obs['interface_refs']):
            claims.append(dict(statement=f'{obs["time"]}: {row["node"]} MTU={row["mtu"]}, admin UP/carrier UP.',evidence_ids=[ident]))
        states=json.loads(next(r.content for r in req.evidence if r.id==obs['graph_ref']))
        claims.append(dict(statement=f'{obs["time"]}: physical UP; peer states={states["peers"]}. Ini observasi, bukan akibat MTU yang terbukti.',
            evidence_ids=[obs['graph_ref']]))
    latest=payload['observations'][-1];left,right=latest['endpoints']
    status='berbeda' if left['mtu']!=right['mtu'] else 'sama'
    text=(f'MTU endpoint terbaru {status}; fase {phase} hanya dalam urutan sampel yang diberikan. '
          'Perbedaan nilai tidak membuktikan gangguan routing, penyebab awal, pelaku, atau keberhasilan perintah perbaikan.')
    ids=[ident for obs in payload['observations'] for ident in obs['interface_refs']]+['H1']
    claims.append(dict(statement=text,evidence_ids=ids))
    claims.append(dict(statement='Dokumentasi OpenConfig mendefinisikan leaf MTU; ini bukan bukti konfigurasi aktif atau MTU yang seharusnya dipilih.',evidence_ids=['D1']))
    response=Response(request_id=req.request_id,status='hypothesis',root_cause_hypothesis=text,claims=claims,
        missing_evidence=['Riwayat sebelum sampel yang disediakan tidak diketahui.'] if phase=='undetermined' else [],proposed_patch=[])
    return validate_pair(req.model_dump(),response.model_dump()).model_dump()

def run(path,output,mode='replay',transport=None):
    output=local_path(output);output.mkdir(parents=True,exist_ok=False)
    audit=dict(status='abstain',model_called=False,llm_requests=0,execution_allowed=False,diagnosis_allowed=False,
        observation_origin='controller_verified_source_values',phase_origin='llm',explanation_origin='bounded_controller_renderer')
    result=abstain('mtu-rejected','Unvalidated evidence')
    try:
        path=local_path(path);audit['sequence']=ref(path)
        req,payload,gates=prepare_input(path,mode)
        result=abstain(req.request_id,'Awaiting validated model output')
        save(output/'input-contract.json',req.model_dump());save(output/'visible-evidence.json',payload);save(output/'source-gates.json',gates)
        # Identity is retained in the audit only; phase model sees ordered MTU pairs.
        pairs=[[r['mtu'] for r in x['endpoints']] for x in payload['observations']]
        relations=['EQUAL' if a==b else 'UNEQUAL' for a,b in pairs]
        data=dict(current_relation=relations[-1],earlier_relations=relations[:-1],
            coverage='complete' if payload['history_complete'] else 'partial')
        save(output/'model-input.json',data)
        audit['comparison_origin']='controller_exact_integer_equality_not_model_arithmetic'
        request,budget=step_request(SYSTEM,data,Phase.model_json_schema(),read(PROFILE))
        save(output/'ollama-request.json',request);save(output/'budget.json',budget)
        audit.update(model_called=True,llm_requests=1)
        raw=(transport or Ollama()).generate(request);save(output/'ollama-response.json',raw);complete_raw(raw,budget)
        value=json.loads(raw['response']);save(output/'raw-phase.json',value);audit['raw_phase']=value
        phase=Phase.model_validate(value).phase
        if phase!=expected_phase(payload):raise ValueError('model_phase_conflicts_with_verified_mtu_history')
        rebuilt,after,_=prepare_input(path,mode)
        if rebuilt!=req or after!=payload:raise ValueError('source_changed_during_inference')
        result=explain(req,payload,phase);audit.update(status='hypothesis',contract_valid=True,phase=phase,
            root_cause_status='not_established',routing_impact='not_established')
    except Exception as exc:
        audit['reason']=type(exc).__name__+':'+str(exc);result=abstain(result['request_id'],audit['reason'])
    save(output/'output-contract.json',result);save(output/'audit.json',audit)
    return audit

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sequence',required=True);p.add_argument('--output',required=True)
    p.add_argument('--mode',choices=['replay','live'],default='replay');a=p.parse_args()
    print(json.dumps(run(a.sequence,a.output,a.mode)))
