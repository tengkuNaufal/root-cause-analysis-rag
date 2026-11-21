"""Read-only operational link RCA over verified frozen evidence."""
import argparse
from copy import deepcopy
import hashlib
import json
import re
import time
import uuid
from typing import Literal

from pydantic import Field, model_validator
from agent_contract.models import Request, Response, Strict, validate_pair
from knowledge.evidence import local_path, read
from reasoning_agent.adapter import Ollama, PROFILE, CONTEXT, OUTPUT, budget, compact, abstain
from reasoning_agent.rca_gate import assess_rca, scoped_events, state_scope

TASK = 'Analyze the current operational state of this link from the cited observations.'
SYSTEM = ('Analyze current link state. active_admin_down means current admin DOWN plus carrier/session loss; '
          'target is that router:interface. no_current_fault means BOTH endpoints admin/carrier UP and sessions healthy; '
          'target null. insufficient_evidence means ambiguous; hypothesis/target null. '
          'Prefer current telemetry over old logs. Docs are mechanisms, not live configuration. '
          'Explain initiating state and protocol effect with D1,T1,T2,G1 and logs when present. '
          'missing_evidence lists unobserved facts, never assessment labels. Initiator unknown. No commands.')

class RcaDraft(Strict):
    assessment: Literal['active_admin_down','no_current_fault','insufficient_evidence']
    hypothesis: str | None = Field(max_length=512)
    target: str | None = Field(max_length=64)
    evidence_ids: list[str] = Field(max_length=6)
    missing_evidence: list[str] = Field(max_length=2)

    @model_validator(mode='after')
    def consistent(self):
        if set(self.missing_evidence)&{'active_admin_down','no_current_fault','insufficient_evidence'}:
            raise ValueError('assessment_labels_are_not_missing_evidence')
        if len(self.evidence_ids)!=len(set(self.evidence_ids)):
            raise ValueError('duplicate_evidence_ids')
        if self.assessment == 'insufficient_evidence':
            if self.hypothesis is not None or self.target is not None or self.evidence_ids or not self.missing_evidence:
                raise ValueError('Inconsistent RCA abstention')
        elif not self.hypothesis or not self.hypothesis.strip() or not self.evidence_ids:
            raise ValueError('RCA explanation and citations required')
        elif self.missing_evidence:
            raise ValueError('admitted_finding_uses_controller_limitations_for_out_of_scope_unknowns')
        if self.assessment == 'active_admin_down' and not self.target:
            raise ValueError('Active finding requires target')
        if self.assessment == 'no_current_fault' and self.target is not None:
            raise ValueError('Healthy state cannot identify an active fault target')
        return self

def select(bundle, gate, request_id, mode):
    e = bundle['evidence']; refs = []; view = {}
    def add(ident, kind, source, locator, content, display):
        refs.append(dict(id=ident,kind=kind,source_path=source['path'],sha256=source['sha256'],
                         locator=locator,content=content))
        view[ident] = display
    d = gate['mechanism']
    add('D1','documentation',dict(path=d['source_path'],sha256=d['sha256']),d['locator'],d['content'],
        re.sub(r'\s+', ' ', d['content']).strip())
    for index, node in enumerate(e['interfaces'],1):
        router, interface, actual = node['router'], node['name'], node['observed']
        obs = next(t for t in e['telemetry'] if t['router']==router and t['source']=='interfaces')
        position = next(i for i, row in enumerate(obs['observation']['data']) if row['name']==interface)
        content = dict(router=router, **{k:actual[k] for k in ('name','admin_up','lower_up','mtu')})
        add(f'T{index}','telemetry',e['inputs']['snapshot'],f'/routers/{router}/sources/interfaces/data/{position}',
            compact(content),f'{router}:{interface} admin={"UP" if actual["admin_up"] else "DOWN"} carrier={"UP" if actual["lower_up"] else "DOWN"} mtu={actual["mtu"]}')
    states = [(s['source'].split(':',1)[1],s['state']) for s in e['sessions']]
    graph_content = dict(physical=e['physical'],sessions=e['sessions'])
    add('G1','graph',e['inputs']['graph'],'/edges',compact(graph_content),
        'physical='+e['physical'][0]['state']+';'+e['focus']['protocol']+'='+','.join(r+':'+s for r,s in states))
    events = scoped_events(e)
    selected = []
    for transition in ('down','up'):
        matching = [row for row in events if row['transition']==transition]
        if matching:
            selected.append(matching[-1])
    sessions = {s['source'].split(':',1)[1]:s for s in e['sessions']}
    for index, item in enumerate(selected,1):
        row = item['row']; event = row['event']; router = event['router']
        if e['focus']['protocol']=='ospf':
            short = 'Full->Deleted(KillNbr)' if item['transition']=='down' else '->Full'
        else:
            short = 'Down Interface down' if item['transition']=='down' else 'Up'
        display = router+' peer='+sessions[router]['peer_address']+' '+short
        source = row['evidence'][0]
        add(f'L{index}','log',source,'line:'+str(source['line']),compact(event),display)
    req = Request(request_id=request_id,question=TASK,mode=mode,snapshot_completed_at=e['window']['end'],
        gate=dict(version=gate['gate_version'],decision=gate['decision'],answer_supported=gate['answer_supported'],reasons=gate['reasons']),
        evidence=refs)
    user = compact(dict(protocol=e['focus']['protocol'],evidence=view))
    if '<|' in user or '|>' in user:
        raise ValueError('model_control_marker_in_data')
    prompt = ('<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n'+SYSTEM+
              '<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n'+user+
              '<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n')
    return req, prompt, budget(prompt), view

def schema(req):
    base = RcaDraft.model_json_schema()
    base['properties']['evidence_ids']['items']['enum'] = [r.id for r in req.evidence]
    active,healthy,uncertain=(deepcopy(base) for _ in range(3))
    active['properties']['assessment']=dict(type='string',const='active_admin_down')
    active['properties']['hypothesis']=dict(type='string',minLength=1)
    active['properties']['target']=dict(type='string',enum=[
        row['router']+':'+row['name'] for r in req.evidence if r.kind=='telemetry' for row in [json.loads(r.content)]])
    active['properties']['evidence_ids']['minItems']=5
    active['properties']['missing_evidence']['maxItems']=0
    healthy['properties']['assessment']=dict(type='string',const='no_current_fault')
    healthy['properties']['hypothesis']=dict(type='string',minLength=1)
    healthy['properties']['target']=dict(type='null')
    healthy['properties']['evidence_ids']['minItems']=4
    healthy['properties']['missing_evidence']['maxItems']=0
    uncertain['properties']['assessment']=dict(type='string',const='insufficient_evidence')
    uncertain['properties']['hypothesis']=dict(type='null')
    uncertain['properties']['target']=dict(type='null')
    uncertain['properties']['evidence_ids']['maxItems']=0
    uncertain['properties']['missing_evidence']['minItems']=1
    return dict(anyOf=[active,healthy,uncertain])

def observed_healthy(req,e):
    if state_scope(e)!='coherent_up_context':
        raise ValueError('healthy_observation_requires_verified_up_context')
    text='No current fault observed on the focus link: both endpoints admin/carrier UP and both '+e['focus']['protocol'].upper()+' peers healthy.'
    response=Response(request_id=req.request_id,status='hypothesis',root_cause_hypothesis=text,
        confidence=None,claims=[dict(statement=text,evidence_ids=['T1','T2','G1'])],
        missing_evidence=[],proposed_patch=[])
    return validate_pair(req.model_dump(),response.model_dump()).model_dump()

def validate_draft(req, raw, allowance, e):
    if raw.get('done') is not True or raw.get('done_reason')!='stop':
        raise ValueError('incomplete_or_truncated_generation')
    count = raw.get('prompt_eval_count'); generated = raw.get('eval_count')
    if type(count) is not int or not 0<count<=allowance['prompt_upper_bound']:
        raise ValueError('unexpected_prompt_token_count')
    if type(generated) is not int or not 0<=generated<=OUTPUT:
        raise ValueError('unexpected_output_token_count')
    draft = RcaDraft.model_validate(json.loads(raw['response']))
    ids = set(draft.evidence_ids); known = {r.id for r in req.evidence}
    if not ids<=known:
        raise ValueError('unknown_evidence_reference')
    if draft.assessment!='insufficient_evidence':
        if not {'D1','T1','T2','G1'}<=ids:
            raise ValueError('missing_cross_source_support')
        scope = state_scope(e)
        if draft.assessment=='no_current_fault' and scope!='coherent_up_context':
            raise ValueError('healthy_claim_conflicts_with_observed_failure')
        if draft.assessment=='active_admin_down':
            if scope!='coherent_admin_down_context':
                raise ValueError('historical_log_must_not_override_current_healthy_state')
            targets = {n['router']+':'+n['name'] for n in e['interfaces'] if n['observed']['admin_up'] is False}
            if draft.target not in targets:
                raise ValueError('wrong_admin_down_target')
            if not any(r.kind=='log' and r.id in ids for r in req.evidence):
                raise ValueError('missing_matching_log_support')
    response = Response(request_id=req.request_id,
        status='abstain' if draft.assessment=='insufficient_evidence' else 'hypothesis',
        root_cause_hypothesis=draft.hypothesis,confidence=None,
        claims=[] if draft.hypothesis is None else [dict(statement=draft.hypothesis,evidence_ids=draft.evidence_ids)],
        missing_evidence=draft.missing_evidence,proposed_patch=[])
    return draft, validate_pair(req.model_dump(), response.model_dump()).model_dump()

def run(bundle_path, output, mode='replay', transport=None):
    output = local_path(output); output.mkdir(parents=True,exist_ok=False)
    ident = 'r-'+uuid.uuid4().hex[:8]
    audit = dict(mode=mode,status='abstain',model_called=False,diagnosis_allowed=False,execution_allowed=False,
                 semantic_validation='structured_finding_target_and_cross_source_checks_only')
    def save(name,data):
        (output/name).write_text(json.dumps(data,indent=2)+'\n')
    started = time.monotonic()
    try:
        path = local_path(bundle_path); content = path.read_bytes(); bundle = json.loads(content)
        audit['bundle'] = dict(path=path.relative_to(local_path('.')).as_posix(),sha256=hashlib.sha256(content).hexdigest())
        gate = assess_rca(bundle,mode)
        save('gate-before.json',gate)
        if not gate['hypothesis_allowed']:
            raise ValueError('rca_gate_abstain:'+','.join(gate['reasons']))
        req,prompt,allowance,view = select(bundle,gate,ident,mode)
        save('input-contract.json',req.model_dump()); save('budget.json',allowance); save('selected-view.json',view)
        (output/'prompt.txt').write_text(prompt)
        if gate['admissible_context']=='coherent_up_context':
            result=observed_healthy(req,bundle['evidence'])
            audit.update(assessment='no_current_fault',target=None,analysis_origin='verified_observation_rule')
        else:
            profile = read(PROFILE)
            payload = dict(model=profile['model'],prompt=prompt,raw=True,stream=False,format=schema(req),keep_alive='5m',
                           options=dict(profile['options'],num_ctx=CONTEXT,num_predict=OUTPUT))
            save('ollama-request.json',payload)
            audit['model_called']=True
            raw = (transport or Ollama()).generate(payload); save('ollama-response.json',raw)
            draft,result = validate_draft(req,raw,allowance,bundle['evidence'])
            save('validated-draft.json',draft.model_dump())
            audit.update(assessment=draft.assessment,target=draft.target,analysis_origin='ollama_hypothesis',
                         prompt_eval_count=raw['prompt_eval_count'],eval_count=raw['eval_count'])
        after = assess_rca(bundle,mode); save('gate-after.json',after)
        if not after['hypothesis_allowed']:
            raise ValueError('post_inference_gate_abstain')
        audit.update(status=result['status'],contract_valid=True)
    except Exception as exc:
        audit['reason']=type(exc).__name__+':'+str(exc)
        result = abstain(ident,audit['reason'])
    save('limitations.json',['Operational hypothesis only; initiator and original command are not observed.',
                             'Snapshot is non-atomic; correlated logs and protocol documentation do not prove all causal claims.',
                             'No remediation, patch or execution is available.'])
    audit['wall_seconds']=time.monotonic()-started
    save('output-contract.json',result); save('audit.json',audit)
    return audit

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',required=True);p.add_argument('--output',required=True)
    p.add_argument('--mode',choices=['replay','live'],default='replay')
    args=p.parse_args(); print(json.dumps(run(args.bundle,args.output,args.mode)))

if __name__=='__main__':
    main()
