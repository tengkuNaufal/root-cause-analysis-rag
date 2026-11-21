"""Audit eight stored temporal explanations and produce checked atomic reports."""
import argparse
from datetime import datetime, timezone
from knowledge.evidence import ROOT, local_path, ref
from reasoning_agent.explanation import load_run, build, validate_report, render
from reasoning_agent.evaluate_negative import save
from knowledge.evidence import read, verify
from reasoning_agent.rca_gate import assess_rca
from reasoning_agent.rca import select, validate_draft
from agent_contract.models import Request, validate_pair

END='data/host1/endpoint-mapping/20261120T135238Z/'
CASES=[('L12-fault',END+'factorial-bound/f1'),('L35-fault',END+'factorial-bound/f5')]+[
    (name,END+'controls-bound/c'+str(i)) for i,name in enumerate(
        ('L12-baseline','L12-recovered','L35-baseline','L35-recovered'),1)]+[
    (link+'-partial','data/host1/negative-partial/20261120T140815Z/evaluation/'+link+'-restored-down_only')
    for link in ('L12','L35')]

def main(output):
    output=local_path(output);output.mkdir(parents=True,exist_ok=False)
    files=('host1/reasoning_agent/explanation.py','host1/reasoning_agent/evaluate_explanations.py',
           'host1/reasoning_agent/test_explanation.py','host1/reasoning_agent/temporal.py','host1/reasoning_agent/rca_gate.py')
    frozen={p:ref(ROOT/p)['sha256'] for p in files}
    inputs={name:{p:ref(local_path(path)/p) for p in ('input-contract.json','output-contract.json',
        'audit.json','visible-evidence.json','ollama-response.json','raw-observations.json','raw-phase.json',
        'combined-model-prediction.json','prompt.txt')} for name,path in CASES}
    save(output/'preregistered.json',dict(at=datetime.now(timezone.utc).isoformat(),code=frozen,inputs=inputs,
        scope='Deterministic bounded rubric and controller reports on known saved runs; no new inference or human score'))
    rows=[]
    for name,path in CASES:
        directory,bundle,req,payload,prediction,result,audit=load_run(path)
        report=build(req,payload,prediction,directory);validate_report(report,req,payload,prediction,directory)
        save(output/(name+'.json'),report);(output/(name+'.md')).write_text(render(report),encoding='utf-8')
        # Explicitly measurable presentation gaps; do not equate citations with entailment of free prose.
        rubric=dict(validated_template_matches_observations=True,
            original_claim_count=len(result['claims']),original_atomic_evidence_mapping=False,
            original_fault_target_named=(prediction['target'] in prediction['explanation']) if prediction['target'] else None,
            original_explicit_initial_cause_boundary=False if prediction['phase']=='fault' else None,
            original_text=prediction['explanation'],original_citations=prediction['citations'],
            original_origin=audit['explanation_origin'],free_llm_prose_scored=False)
        rows.append(dict(case=name,phase=prediction['phase'],original_review=rubric,
            report_valid=True,atomic_claims=len(report['claims']),root_cause_status=report['root_cause_status']))
    legacy=[]
    for link in ('L12','L35'):
        directory=local_path('data/host1/rca-agent/20261120T114204Z/hybrid-v1/actual/'+link+'-down')
        audit=read(directory/'audit.json');bundle=read(verify(audit['bundle']['path'],audit['bundle']['sha256']))
        req=Request.model_validate(read(directory/'input-contract.json'));gate=assess_rca(bundle,audit['mode'])
        if not gate['hypothesis_allowed']:raise ValueError('Legacy source no longer admitted')
        rebuilt,prompt,allowance,_=select(bundle,gate,req.request_id,audit['mode'])
        if rebuilt!=req:raise ValueError('Legacy request differs from source')
        draft,result=validate_draft(req,read(directory/'ollama-response.json'),allowance,bundle['evidence'])
        saved=read(directory/'output-contract.json');validate_pair(req.model_dump(),saved)
        if saved!=result:raise ValueError('Legacy raw response differs from saved contract')
        legacy.append(dict(link=link,source_contract=ref(directory/'output-contract.json'),
            text=draft.hypothesis,citations=draft.evidence_ids,
            provenance_and_contract_revalidated=True,review_origin='assistant_qualitative_review_not_independent_human',
            limitations=(['Admin DOWN and carrier loss are not separated into contributing condition versus symptom.',
                          'No explicit distinction from unobserved initial cause or initiator.'] if link=='L12' else
                         ['Target is named but no explanatory condition, symptom or mechanism is stated.',
                          'Citation list alone does not explain which observation supports the conclusion.'])))
    save(output/'legacy-prose-review.json',legacy)
    for p,sha in frozen.items():
        if ref(ROOT/p)['sha256']!=sha:raise ValueError('Code changed during evaluation')
    for refs in inputs.values():
        for p,entry in refs.items():
            if ref(entry['path'])!=entry:raise ValueError('Saved input changed during evaluation')
    summary=dict(cases=rows,total=len(rows),reports_valid=sum(r['report_valid'] for r in rows),
        atomic_claims=sum(r['atomic_claims'] for r in rows),code_and_inputs_unchanged=True,
        legacy_prose_reviews=len(legacy),new_llm_requests=0,execution_allowed=False,
        limitation='Fixed claim vocabulary and exact render validation; not general semantic entailment or independent prose grading')
    save(output/'summary.json',summary);print(__import__('json').dumps(summary,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output');main(p.parse_args().output)
