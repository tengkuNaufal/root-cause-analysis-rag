"""LLM-only state/temporal classification over verified cited views; no healthy shortcut."""
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
from knowledge.evidence import local_path, read, instant
from reasoning_agent.adapter import Ollama, PROFILE, compact, abstain
from reasoning_agent.rca import select as select_rca
from reasoning_agent.rca_gate import assess_rca, state_scope

OUTPUT=256
SYSTEM=('Choose phase from model_observations. Return JSON with only phase. No commands or actor/config claims. '
        'Examples with unrelated nodes: '
        'admin_down=[X:if0],physical=down,peers=[Active,Active] => fault. '
        'admin_down=[],physical=up,peers=[Full/-,Full/-],coverage=complete,events=[] => baseline. '
        'admin_down=[],physical=up,peers=[Established,Established],coverage=complete,events=[] => baseline. '
        'admin_down=[],physical=up,peers=[Full/-,Full/-],coverage=complete,events=[DOWN,UP] => recovered. '
        'admin_down=[],physical=up,peers=[Established,Established],coverage=complete,events=[DOWN,UP] => recovered. '
        'admin_down=[],physical=up,peers=[Established,Established],coverage=partial,events=[DOWN] or [] => undetermined. '
        'Current faults take priority over history. Full and Established mean healthy peers.')
OBSERVATION_SYSTEM=('Extract facts only. admin_down lists nodes with admin_up=false; carrier_down lists nodes with carrier_up=false. '
    'peer_states copies the two peer_state strings in interface list order. Copy graph physical and history complete. '
    'events_time_order lists event values sorted by timestamp, not list order. Use empty lists when none. Do not classify phase.')

class ObservationDraft(Strict):
    admin_down: list[str] = Field(max_length=2)
    carrier_down: list[str] = Field(max_length=2)
    peer_states: list[str] = Field(min_length=2,max_length=2)
    physical: Literal['up','down']
    history_complete: bool
    events_time_order: list[Literal['DOWN','UP']] = Field(max_length=2)

def expected_observations(payload):
    rows=payload['current']['interfaces'];events=sorted(payload['history']['events'],key=lambda x:instant(x['time']))
    return dict(admin_down=sorted(r['node'] for r in rows if not r['admin_up']),
        carrier_down=sorted(r['node'] for r in rows if not r['carrier_up']),
        peer_states=[r['peer_state'] for r in rows],
        physical=payload['current']['graph']['physical'],history_complete=payload['history']['complete'],
        events_time_order=[r['event'] for r in events])

def validate_observations(value,payload):
    draft=ObservationDraft.model_validate(value);actual=draft.model_dump()
    actual['admin_down']=sorted(actual['admin_down']);actual['carrier_down']=sorted(actual['carrier_down'])
    if actual!=expected_observations(payload):raise ValueError('llm_fact_extraction_conflicts_with_sources')
    return draft

class PhaseDraft(Strict):
    phase: Literal['baseline','fault','recovered','undetermined']

def combine_model_outputs(observations,phase,payload):
    """Map two model outputs to metadata; never choose or change the phase."""
    target=observations.admin_down[0] if phase.phase=='fault' and len(observations.admin_down)==1 else None
    descriptions=dict(baseline='Healthy at this snapshot; no DOWN/UP transition in the complete provided history.',
        fault='An administrative-down condition with carrier/protocol loss is observed.',
        recovered='Healthy at this snapshot; provided history records DOWN followed by UP.',
        undetermined='Healthy at this snapshot; supplied history cannot establish baseline versus recovery.')
    citations=list(payload['required_current_refs'])
    if phase.phase in ('fault','recovered'):
        citations.extend(x['ref'] for x in payload['history']['events'])
    return dict(current='fault' if phase.phase=='fault' else 'healthy',phase=phase.phase,target=target,
                explanation=descriptions[phase.phase],citations=citations)

def frame(system,data):
    return ('<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n'+system+
        '<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n'+compact(data)+
        '<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n')

def token_budget(prompt):
    report=dict(method='utf8_byte_upper_bound_for_pinned_llama3',prompt_upper_bound=len(prompt.encode()),
                output_reserved=OUTPUT,overhead_reserved=64,num_ctx=2048)
    if report['prompt_upper_bound']+OUTPUT+64>2048:raise ValueError('context_budget_exceeded')
    return report

def complete_raw(raw,allowance):
    if raw.get('done') is not True or raw.get('done_reason')!='stop':raise ValueError('incomplete_generation')
    n=raw.get('prompt_eval_count');k=raw.get('eval_count')
    if type(n) is not int or not 0<n<=allowance['prompt_upper_bound']:raise ValueError('unexpected_prompt_tokens')
    if type(k) is not int or not 0<=k<=OUTPUT:raise ValueError('unexpected_output_tokens')

class EndpointState(Strict):
    admin_up: bool
    carrier_up: bool
    peer_state: str = Field(min_length=1,max_length=32)

class HistoryContext(Strict):
    physical: Literal['up','down']
    history_complete: bool
    events_time_order: list[Literal['DOWN','UP']] = Field(max_length=2)

ENDPOINT_SYSTEM=('Copy admin_up, carrier_up and peer_state exactly from this ONE source endpoint. '
    'Return only these three fields. Carrier can be false while admin is true; do not replace admin_up with carrier_up. '
    'Do not select another endpoint, infer a fault or change a boolean.')
CONTEXT_SYSTEM=('Copy graph.physical and history.complete. Sort history events by timestamp and list their event values '
    'as events_time_order. Use an empty list when no events are given. Do not classify phase.')

def step_request(system,data,schema,profile):
    prompt=frame(system,data);allowance=token_budget(prompt)
    return dict(model=profile['model'],prompt=prompt,raw=True,stream=False,format=schema,keep_alive='5m',
                options=dict(profile['options'],num_ctx=2048,num_predict=OUTPUT)),allowance

def grouped_request(payload,profile):
    schema=ObservationDraft.model_json_schema()
    for name in ('admin_down','carrier_down'):
        schema['properties'][name]['items']['enum']=[x['node'] for x in payload['current']['interfaces']]
    schema['properties']['peer_states']['items']['enum']=sorted({x['peer_state'] for x in payload['current']['interfaces']})
    return step_request(OBSERVATION_SYSTEM,dict(current=payload['current'],history=payload['history']),schema,profile)

def endpoint_input(row):
    # Identity belongs to the source row, not a model-selected index. Citation IDs
    # stay in the binding artifact and cannot affect the inference prompt.
    return dict(source_endpoint={key:row[key] for key in ('node','admin_up','carrier_up','peer_state')})

def context_input(payload):
    return dict(graph=dict(physical=payload['current']['graph']['physical']),
                history=dict(complete=payload['history']['complete'],
                    events=[dict(time=e['time'],event=e['event']) for e in payload['history']['events']]))

def validate_endpoint(value,row):
    result=EndpointState.model_validate(value)
    if result.model_dump()!={key:row[key] for key in ('admin_up','carrier_up','peer_state')}:
        raise ValueError('endpoint_value_conflicts_with_bound_source:'+row['node'])
    return result

def extract_observations(client,payload,profile,save,audit,extractor):
    def generate(name,request,allowance):
        save(name+'-budget.json',allowance);save(name+'-request.json',request)
        audit['model_called']=True;audit['llm_requests']+=1
        raw=client.generate(request);save(name+'-response.json',raw);complete_raw(raw,allowance)
        value=json.loads(raw['response']);save(name+'-raw.json',value)
        return value
    if extractor=='grouped':
        request,allowance=grouped_request(payload,profile)
        value=generate('observation',request,allowance);save('raw-observations.json',value)
        return validate_observations(value,payload)
    if extractor!='bound':raise ValueError('unsupported_extractor')
    bindings=[];peer_vocabulary=sorted({row['peer_state'] for row in payload['current']['interfaces']})
    for index,row in enumerate(payload['current']['interfaces'],1):
        schema=EndpointState.model_json_schema();schema['properties']['peer_state']['enum']=peer_vocabulary
        request,allowance=step_request(ENDPOINT_SYSTEM,endpoint_input(row),schema,profile)
        # Save the trusted node/ref before sending a request; neither is selected
        # from the response, and raw incorrect values are never overwritten.
        save(f'endpoint-{index}-binding.json',dict(node=row['node'],citation=row['ref']))
        value=generate(f'endpoint-{index}',request,allowance)
        values=validate_endpoint(value,row)
        bindings.append(dict(node=row['node'],citation=row['ref'],model_values=values.model_dump()))
        audit['endpoint_rows_validated']=len(bindings)
    request,allowance=step_request(CONTEXT_SYSTEM,context_input(payload),HistoryContext.model_json_schema(),profile)
    context=HistoryContext.model_validate(generate('history-context',request,allowance))
    value=dict(admin_down=[r['node'] for r in bindings if not r['model_values']['admin_up']],
        carrier_down=[r['node'] for r in bindings if not r['model_values']['carrier_up']],
        peer_states=[r['model_values']['peer_state'] for r in bindings],**context.model_dump())
    save('endpoint-bindings.json',bindings);save('raw-observations.json',value)
    audit['observation_origin']='model_values_aggregated_with_controller_owned_source_identity'
    return validate_observations(value,payload)

class TemporalDraft(Strict):
    current: Literal['healthy','fault','uncertain']
    phase: Literal['baseline','fault','recovered','undetermined']
    target: str | None = Field(max_length=64)
    explanation: str = Field(min_length=1,max_length=240)
    citations: list[str] = Field(min_length=1,max_length=6)

    @model_validator(mode='after')
    def consistent(self):
        if len(self.citations)!=len(set(self.citations)):raise ValueError('duplicate_citations')
        if self.phase=='fault' and (self.current!='fault' or not self.target):raise ValueError('inconsistent_fault')
        if self.phase in ('baseline','recovered') and (self.current!='healthy' or self.target is not None):raise ValueError('inconsistent_healthy_phase')
        if self.current!='fault' and self.target is not None:raise ValueError('target_without_current_fault')
        return self

def view(bundle,gate,ident,mode='replay',options=None):
    options=options or {}
    allowed={'reverse_endpoints','opaque_ids','reverse_events','history','doc_last','citation_map'}
    if not set(options)<=allowed or options.get('history','all') not in ('all','down_only','none'):
        raise ValueError('unsupported_view_transformation')
    old,_,_,_=select_rca(bundle,gate,ident,mode)
    e=bundle['evidence'];refs=list(old.evidence)
    logs=[r for r in refs if r.kind=='log']
    history_mode=options.get('history','all')
    if history_mode=='none':logs=[]
    if history_mode=='down_only':
        logs=[r for r in logs if ' Down Interface down' in json.loads(r.content)['message'] or 'Full -> Deleted (KillNbr)' in json.loads(r.content)['message']]
    refs=[r for r in refs if r.kind!='log']+logs
    mapping={'D1':'K4','T1':'P7','T2':'B2','G1':'J9','L1':'C3','L2':'V8'} if options.get('opaque_ids') else {r.id:r.id for r in refs}
    if 'citation_map' in options:
        replacement=options['citation_map']
        if (options.get('opaque_ids') or not isinstance(replacement,dict)
            or not {r.id for r in refs}<=set(replacement)
            or any(not isinstance(v,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9]{1,7}',v) for v in replacement.values())
            or len(set(replacement.values()))!=len(replacement)):
            raise ValueError('invalid_citation_map')
        mapping=replacement
    selected=[]
    for r in refs:
        value=r.model_dump();value['id']=mapping[r.id];selected.append(value)
    rows=[]
    session={s['source'].split(':',1)[1]:s for s in e['sessions']}
    for index,node in enumerate(e['interfaces'],1):
        o=node['observed'];rows.append(dict(ref=mapping[f'T{index}'],node=node['router']+':'+node['name'],
            admin_up=o['admin_up'],carrier_up=o['lower_up'],peer_state=session[node['router']]['state']))
    if options.get('reverse_endpoints'):rows.reverse()
    events=[]
    for r in logs:
        event=json.loads(r.content)
        down=' Down Interface down' in event['message'] or 'Full -> Deleted (KillNbr)' in event['message']
        events.append(dict(ref=mapping[r.id],time=event['event_timestamp'],event='DOWN' if down else 'UP'))
    events.sort(key=lambda row:instant(row['time']))
    if options.get('reverse_events'):events.reverse()
    doc=next(r for r in refs if r.kind=='documentation')
    document=dict(ref=mapping['D1'],text=re.sub(r'\s+',' ',doc.content).strip())
    history=dict(complete=history_mode=='all',events=events)
    current=dict(interfaces=rows,graph=dict(ref=mapping['G1'],physical=e['physical'][0]['state']),protocol=e['focus']['protocol'])
    mandatory=[row['ref'] for row in rows]+[mapping['G1']]
    payload=dict(documentation=document,history=history,current=current,required_current_refs=mandatory)
    if options.get('doc_last'):payload=dict(history=history,current=current,required_current_refs=mandatory,documentation=document)
    req=Request(request_id=ident,question='Classify current state and phase within the supplied observation window.',
        mode=mode,snapshot_completed_at=old.snapshot_completed_at,
        gate=dict(version='temporal-1.0/'+gate['gate_version'],decision=gate['decision'],answer_supported=gate['answer_supported'],reasons=gate['reasons']),evidence=selected)
    data=compact(payload)
    if '<|' in data or '|>' in data:raise ValueError('control_marker_in_data')
    prompt=('<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\nVerified source selection for audit (not an inference prompt).'+
            '<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n'+data+
            '<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n')
    allowance=dict(method='utf8_byte_upper_bound_for_pinned_llama3',prompt_upper_bound=len(prompt.encode()),
                   output_reserved=OUTPUT,overhead_reserved=64,num_ctx=2048)
    if allowance['prompt_upper_bound']+OUTPUT+64>2048:raise ValueError('context_budget_exceeded')
    return req,payload,prompt,allowance

def supported_outcome(e,payload):
    """Post-inference fact check only; this result is never sent to the model."""
    if state_scope(e)=='coherent_admin_down_context':
        node=next(n for n in e['interfaces'] if n['observed']['admin_up'] is False)
        return dict(current='fault',phase='fault',target=node['router']+':'+node['name'])
    history=payload['history'];events=history['events']
    phase='undetermined'
    if history['complete']:
        down=[instant(x['time']) for x in events if x['event']=='DOWN']
        up=[instant(x['time']) for x in events if x['event']=='UP']
        if down and up and max(up)>max(down):phase='recovered'
        elif not down and not up:phase='baseline'
    return dict(current='healthy',phase=phase,target=None)

def validate_prediction(req,raw,allowance,e,payload):
    complete_raw(raw,allowance)
    draft=TemporalDraft.model_validate(json.loads(raw['response']))
    ids=set(draft.citations);known={r.id for r in req.evidence}
    if not ids<=known:raise ValueError('unknown_citation')
    expected=supported_outcome(e,payload)
    if any(getattr(draft,key)!=value for key,value in expected.items()):raise ValueError('prediction_conflicts_with_visible_evidence')
    required={row['ref'] for row in payload['current']['interfaces']}|{payload['current']['graph']['ref']}
    if draft.phase=='recovered':required|={row['ref'] for row in payload['history']['events']}
    if not required<=ids:raise ValueError('missing_current_or_temporal_citation')
    result=Response(request_id=req.request_id,status='hypothesis',root_cause_hypothesis=draft.explanation,
        confidence=None,claims=[dict(statement=draft.explanation,evidence_ids=draft.citations)],
        missing_evidence=['History is insufficient to distinguish baseline from recovery.'] if draft.phase=='undetermined' else [],proposed_patch=[])
    return draft,validate_pair(req.model_dump(),result.model_dump()).model_dump()

def run(bundle_path,output,options=None,mode='replay',transport=None,extractor='bound'):
    output=local_path(output);output.mkdir(parents=True,exist_ok=False)
    audit=dict(model_called=False,llm_requests=0,status='abstain',analysis_origin='source_bound_llm_temporal_no_rule_substitution' if extractor=='bound' else 'two_stage_llm_temporal_no_rule_substitution',
               execution_allowed=False,diagnosis_allowed=False,mode=mode,options=options or {},extractor=extractor)
    def save(name,value):(output/name).write_text(json.dumps(value,indent=2)+'\n')
    started=time.monotonic();ident='t-'+uuid.uuid4().hex[:8]
    try:
        source=local_path(bundle_path);data=source.read_bytes();bundle=json.loads(data)
        audit['bundle']=dict(path=str(source.relative_to(local_path('.'))),sha256=hashlib.sha256(data).hexdigest())
        gate=assess_rca(bundle,mode);save('gate-before.json',gate)
        if not gate['hypothesis_allowed']:raise ValueError('source_gate_abstain')
        req,payload,_,_=view(bundle,gate,ident,mode,options)
        save('input-contract.json',req.model_dump());save('visible-evidence.json',payload)
        profile=read(PROFILE);client=transport or Ollama()
        observations=extract_observations(client,payload,profile,save,audit,extractor);audit['facts_validated']=True
        summary=observations.model_dump();summary['coverage']='complete' if summary.pop('history_complete') else 'partial'
        summary['events']=summary.pop('events_time_order')
        if extractor=='bound':
            # Only presentation is canonicalized AFTER every model value was
            # verified. This never fixes a wrong boolean or chooses a phase.
            for name in ('admin_down','carrier_down','peer_states'):summary[name]=sorted(summary[name])
            audit['phase_input_normalization']='sorted_verified_model_lists'
        reasoning_input=dict(model_observations=summary)
        prompt=frame(SYSTEM,reasoning_input);allowance=token_budget(prompt)
        save('budget.json',allowance);save('reasoning-input.json',reasoning_input);(output/'prompt.txt').write_text(prompt)
        wire=PhaseDraft.model_json_schema()
        request=dict(model=profile['model'],prompt=prompt,raw=True,stream=False,format=wire,keep_alive='5m',
                     options=dict(profile['options'],num_ctx=2048,num_predict=OUTPUT))
        save('ollama-request.json',request);audit['llm_requests']+=1
        raw=client.generate(request);save('ollama-response.json',raw)
        phase_value=json.loads(raw['response']);save('raw-phase.json',phase_value);audit['raw_phase_prediction']=phase_value
        phase=PhaseDraft.model_validate(phase_value)
        prediction=combine_model_outputs(observations,phase,payload)
        save('combined-model-prediction.json',prediction);audit['raw_prediction']=prediction
        audit['explanation_origin']='controller_rendering_of_model_chosen_phase'
        audit['citation_origin']='controller_binding_of_verified_source_refs'
        draft,result=validate_prediction(req,dict(raw,response=compact(prediction)),allowance,bundle['evidence'],payload)
        after=assess_rca(bundle,mode);save('gate-after.json',after)
        if not after['hypothesis_allowed']:raise ValueError('post_inference_gate_abstain')
        audit.update(status='hypothesis',contract_valid=True,prompt_eval_count=raw['prompt_eval_count'],eval_count=raw['eval_count'])
    except Exception as exc:
        audit['reason']=type(exc).__name__+':'+str(exc);result=abstain(ident,audit['reason'])
    audit['wall_seconds']=time.monotonic()-started
    save('output-contract.json',result);save('audit.json',audit)
    return audit

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',required=True);p.add_argument('--output',required=True)
    p.add_argument('--mode',choices=['replay','live'],default='replay')
    p.add_argument('--extractor',choices=['bound','grouped'],default='bound');a=p.parse_args()
    print(json.dumps(run(a.bundle,a.output,mode=a.mode,extractor=a.extractor)))
