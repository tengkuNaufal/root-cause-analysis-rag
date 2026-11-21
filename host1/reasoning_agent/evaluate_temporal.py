"""Score raw LLM decisions separately from contract/gate acceptance on frozen cases."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from knowledge.evidence import ROOT, local_path, read, verify
from reasoning_agent.temporal import run, view, TemporalDraft
from reasoning_agent.rca_gate import assess_rca

FILES=['host1/reasoning_agent/temporal.py','host1/reasoning_agent/evaluate_temporal.py','host1/reasoning_agent/rca.py',
       'host1/reasoning_agent/rca_gate.py','host1/reasoning_agent/adapter.py','host1/agent_contract/models.py','host1/ollama_host/inference-profile.json']

def fingerprints():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}

def score_prediction(raw,expected):
    value=raw if isinstance(raw,dict) else {}
    state_phase=value.get('current')==expected['state'] and value.get('phase')==expected['phase']
    try:TemporalDraft.model_validate(value);valid=True
    except (ValueError,TypeError):valid=False
    return dict(raw_state_phase_correct=state_phase,
                raw_classification_correct=state_phase and value.get('target')==expected['target'],draft_valid=valid)

def main(directory,stage,label,preflight=False,extractor='bound'):
    directory=local_path(directory);registered=read(directory/'preregistered.json')
    for name,digest in registered['hashes'].items():verify(directory/name,digest)
    cases=read(directory/('variations.json' if stage=='variations' else 'development.json'))
    expected=read(directory/'expected.json')
    output=directory/label;output.mkdir(exist_ok=False)
    code=fingerprints()
    freeze=dict(at=datetime.now(timezone.utc).isoformat(),code=code,stage=stage,extractor=extractor,model_profile=read(ROOT/'host1/ollama_host/inference-profile.json'))
    (output/'implementation-freeze.json').write_text(json.dumps(freeze,indent=2))
    rows=[]
    for case in cases:
        source=verify(case['bundle'],case['sha256'])
        if fingerprints()!=code:raise ValueError('Implementation changed during evaluation')
        if preflight:
            bundle=read(source);gate=assess_rca(bundle)
            if not gate['hypothesis_allowed']:raise ValueError('Source gate abstains')
            req,payload,prompt,allowance=view(bundle,gate,'preflight',options=case['options'])
            row=dict(id=case['id'],passed=True,budget=allowance)
        else:
            audit=run(source,output/case['id'],options=case['options'],extractor=extractor)
            raw=audit.get('raw_prediction',{})
            phase=audit.get('raw_phase_prediction',raw)
            row=dict(id=case['id'],expected=expected[case['id']],raw_prediction=raw,
                     model_called=audit['model_called'],**score_prediction(raw,expected[case['id']]),
                     raw_phase_correct=isinstance(phase,dict) and phase.get('phase')==expected[case['id']]['phase'],
                     facts_validated=audit.get('facts_validated',False),llm_requests=audit.get('llm_requests',1 if audit['model_called'] else 0),
                     contract_accepted=audit.get('contract_valid') is True,status=audit['status'],
                     reason=audit.get('reason'),wall_seconds=audit['wall_seconds'])
        rows.append(row);print(json.dumps(row),flush=True)
    report=dict(stage=stage,preflight=preflight,extractor=extractor,cases=rows,total=len(rows),
        raw_correct=sum(r.get('raw_classification_correct',False) for r in rows),
        state_phase_correct=sum(r.get('raw_state_phase_correct',False) for r in rows),
        raw_phase_correct=sum(r.get('raw_phase_correct',False) for r in rows),
        draft_valid=sum(r.get('draft_valid',False) for r in rows),
        accepted=sum(r.get('contract_accepted',False) for r in rows),
        model_calls=sum(r.get('model_called',False) for r in rows),
        llm_requests=sum(r.get('llm_requests',0) for r in rows),facts_validated=sum(r.get('facts_validated',False) for r in rows),
        scope='Frozen assistant-designed perturbations of known traces, not independent fault accuracy or human evaluation')
    (output/'summary.json').write_text(json.dumps(report,indent=2))
    return 0

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory');p.add_argument('--stage',choices=['development','variations'],required=True)
    p.add_argument('--label',required=True);p.add_argument('--preflight',action='store_true')
    p.add_argument('--extractor',choices=['bound','grouped'],default='bound');a=p.parse_args()
    raise SystemExit(main(a.directory,a.stage,a.label,a.preflight,a.extractor))
