"""Paired factorial evaluation; case labels never enter inference requests."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from knowledge.evidence import ROOT, local_path, read, verify
from reasoning_agent.evaluate_temporal import score_prediction, fingerprints as temporal_fingerprints
from reasoning_agent.temporal import run, view
from reasoning_agent.rca_gate import assess_rca

def fingerprints():
    values=temporal_fingerprints()
    for name in ('host1/reasoning_agent/evaluate_endpoints.py','host1/reasoning_agent/freeze_endpoint_cases.py'):
        values[name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    return values

def main(directory,suite,extractor,label,preflight=False):
    directory=local_path(directory);registered=read(directory/'preregistered.json')
    for name,digest in registered['hashes'].items():verify(directory/name,digest)
    cases=read(directory/(suite+'.json'));expected=read(directory/'expected.json')
    output=directory/label;output.mkdir(exist_ok=False);code=fingerprints()
    (output/'implementation-freeze.json').write_text(json.dumps(dict(code=code,suite=suite,extractor=extractor,
        at=datetime.now(timezone.utc).isoformat(),model_profile=read(ROOT/'host1/ollama_host/inference-profile.json')),indent=2))
    rows=[]
    for case in cases:
        if code!=fingerprints():raise ValueError('Implementation changed during evaluation')
        source=verify(case['bundle'],case['sha256'])
        if preflight:
            bundle=read(source);gate=assess_rca(bundle)
            if not gate['hypothesis_allowed']:raise ValueError('Source gate abstains')
            req,payload,prompt,allowance=view(bundle,gate,'preflight',options=case['options'])
            item=dict(id=case['id'],passed=True,budget=allowance)
        else:
            audit=run(source,output/case['id'],options=case['options'],extractor=extractor)
            raw=audit.get('raw_prediction',{});phase=audit.get('raw_phase_prediction',{})
            item=dict(id=case['id'],link=case['link'],role=case['role'],factors=case['factors'],expected=expected[case['id']],
                **score_prediction(raw,expected[case['id']]),raw_phase_correct=phase.get('phase')==expected[case['id']]['phase'],
                facts_validated=audit.get('facts_validated',False),contract_accepted=audit.get('contract_valid',False),
                model_called=audit['model_called'],llm_requests=audit['llm_requests'],reason=audit.get('reason'),
                raw_prediction=raw,wall_seconds=audit['wall_seconds'])
        rows.append(item);print(json.dumps(item),flush=True)
    if code!=fingerprints():raise ValueError('Implementation changed during final case')
    report=dict(suite=suite,extractor=extractor,preflight=preflight,total=len(rows),cases=rows,
        facts_validated=sum(r.get('facts_validated',False) for r in rows),raw_phase_correct=sum(r.get('raw_phase_correct',False) for r in rows),
        accepted=sum(r.get('contract_accepted',False) for r in rows),llm_requests=sum(r.get('llm_requests',0) for r in rows),
        scope='Paired presentation-factor checks on two stored fault traces; single run per cell, not independent network accuracy')
    (output/'summary.json').write_text(json.dumps(report,indent=2));return 0

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory')
    p.add_argument('--suite',choices=['development','factorial','controls'],required=True)
    p.add_argument('--extractor',choices=['bound','grouped'],required=True);p.add_argument('--label',required=True)
    p.add_argument('--preflight',action='store_true');a=p.parse_args()
    raise SystemExit(main(a.directory,a.suite,a.extractor,a.label,a.preflight))
