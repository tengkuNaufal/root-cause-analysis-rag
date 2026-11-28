"""Deterministic synthetic examples; no lab, model or catalog imports."""
import json
from pathlib import Path
from pydantic.json_schema import models_json_schema
from .models import (VERSION, DiagnosisRequest, Job, EvidencePayload, LintInput,
                     LintOutput, ErrorResponse, Health, Capabilities, WireResponse,
                     LiveHealth, LiveCapabilities, validate_live_pair, digest, project)

STAMP = '2026-11-21T00:00:00Z'
RID = '00000000-0000-4000-8000-000000000001'
JID = '00000000-0000-4000-8000-000000000002'
SOURCE = {'synthetic': True, 'local_mtu': 1400, 'peer_mtu': 1500}

def request():
    return dict(contract_version=VERSION, request_id=RID, lab='rca', variant='graph_rag',
                symptom_detected_at_utc=STAMP, execution_allowed=False)

def pending(req, job_id, stamp=STAMP):
    return dict(contract_version=VERSION, request_id=req['request_id'], job_id=job_id,
                mode='live', lab='rca', variant=req['variant'], state='accepted',
                received_at=stamp, updated_at=stamp, execution_allowed=False, simulation=True)

def evidence():
    sha = digest(SOURCE)
    return dict(id='e1', kind='telemetry', source_id='sha256:'+sha,
                source_sha256=sha, locator='/', content=json.dumps(SOURCE, sort_keys=True))

def terminal(base, outcome='hypothesis', elapsed=0.0):
    value = dict(base)
    if outcome in ('failed', 'interrupted'):
        value.update(state=outcome, error=dict(code='mock_'+outcome,
                     message='Synthetic mock outcome; no backend or router was called.', retryable=False))
        return Job.model_validate(value).model_dump()
    abstain = outcome == 'abstain'
    ev = evidence()
    patch = [] if abstain else [dict(router='r1', interface='eth1', interpreter='linux_argv',
             arguments=['ip','link','set','eth1','mtu','1500'], evidence_ids=['e1'],
             rationale='Synthetic proposal only; not executed.', validation_status='unvalidated')]
    result = dict(schema_version=1, request_id=base['request_id'],
                  status='abstain' if abstain else 'hypothesis',
                  root_cause_hypothesis=None if abstain else 'Synthetic fixture: unequal MTU values.',
                  root_cause_class=None if abstain else 'mtu_mismatch',
                  root_cause_router=None if abstain else 'r1',
                  confidence=None if abstain else 0.5,
                  claims=[] if abstain else [dict(statement='Synthetic MTU values differ.', evidence_ids=['e1'])],
                  missing_evidence=['Mock intentionally abstains.'] if abstain else [],
                  proposed_patch=patch, execution_allowed=False)
    agent_req = dict(schema_version=1, request_id=base['request_id'], lab='rca',
         question='Synthetic contract test only.', mode='live', snapshot_completed_at=base['updated_at'],
         gate=dict(version='mock', decision='abstain' if abstain else 'context_ready',
                   answer_supported=not abstain, reasons=['Synthetic fixture']),
         evidence=[dict(id='e1',kind='telemetry',source_path='mock-source',sha256=ev['source_sha256'],
                        locator='/',content=ev['content'])], execution_allowed=False)
    validated = validate_live_pair(agent_req, result)
    manifest = {k:v for k,v in ev.items() if k!='content'}
    manifest.update(url=f"/v1/diagnoses/{base['job_id']}/evidence/e1",
                    capture_started_at=base['updated_at'], capture_completed_at=base['updated_at'])
    value.update(state='completed', result=validated.model_dump(),
        assessment=dict(router=validated.root_cause_router, root_cause=validated.root_cause_class or 'unknown',
              confidence=result['confidence'], evidence_ids=[] if abstain else ['e1'],
              commands=[c.model_dump() for c in project(validated.proposed_patch)],
              explanation='Synthetic mock abstention.' if abstain else 'Synthetic fixture only; no real diagnosis.'),
        evidence=[manifest], timing=dict(collection_seconds=0.0, retrieval_seconds=0.0,
                    reasoning_seconds=elapsed, validation_seconds=0.0, total_seconds=elapsed),
        provenance=dict(synthetic=True, inventory_sha256=digest({'inventory':'synthetic'}),
            capture_sha256=ev['source_sha256'], agent_version='mock-1',gate_version='mock-1',
            prompt_version='not_used',retriever_version='not_used',model_profile='not_used',
            model_digest='0'*64,model_options={},actual_variant=base['variant'],model_evidence_ids=[],
            selection_notes=['No model/retriever used. All three variants return synthetic fixtures.'],
            evidence_age_at_reasoning_seconds=0.0,evidence_age_at_completion_seconds=elapsed))
    return Job.model_validate(value).model_dump()

def examples():
    req=request(); base=pending(req,JID); completed=terminal(base)
    commands=completed['assessment']['commands']
    li=dict(contract_version=VERSION,job_id=JID,inventory_sha256=completed['provenance']['inventory_sha256'],
            commands=commands,commands_sha256=digest(commands))
    lo=dict(job_id=JID,commands_sha256=li['commands_sha256'],inventory_sha256=li['inventory_sha256'],
            linter_version='synthetic-only',policy_version='synthetic-only',policy_sha256='0'*64,
            status='passed',violations=[],checked_at=STAMP)
    return dict(request=req,pending=base,hypothesis=completed,abstain=terminal(base,'abstain'),
                failed=terminal(base,'failed'),interrupted=terminal(base,'interrupted'),
                evidence=evidence(),lint_input=li,lint_output=lo,
                error=dict(contract_version=VERSION,request_id=None,
                           error=dict(code='invalid_request',message='Synthetic example.',retryable=False)))

def schema():
    types=[DiagnosisRequest,WireResponse,Job,EvidencePayload,LintInput,LintOutput,ErrorResponse,Health,Capabilities,LiveHealth,LiveCapabilities]
    refs, shared=models_json_schema([(t,'validation') for t in types])
    return {'$schema':'https://json-schema.org/draft/2020-12/schema',
            'title':'Live API draft 2 payload definitions', **shared,
            'x-payload-schemas':{t.__name__:refs[(t,'validation')] for t in types}}

def main():
    here=Path(__file__).resolve().parent
    for name,value in [('schema.json',schema()),('examples.json',examples())]:
        (here/name).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')

if __name__=='__main__':
    main()
