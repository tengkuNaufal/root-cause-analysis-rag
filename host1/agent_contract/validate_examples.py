"""Export schemas and test synthetic contract examples, never call a model."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from agent_contract.models import Request, Response, validate_pair

def main(out):
    out.mkdir(parents=True, exist_ok=False)
    for name, model in [('input',Request),('output',Response)]:
        (out/(name+'.schema.json')).write_text(json.dumps(model.model_json_schema(),indent=2)+'\n')
    request = dict(request_id='synthetic-contract-test', question='Is there enough evidence?', mode='replay',snapshot_completed_at='2026-11-19T15:00:00Z',
        gate=dict(version='2.1',decision='abstain',answer_supported=False,reasons=['missing_claim_support']),
        evidence=[dict(id='synthetic-ref',kind='telemetry',source_path='synthetic-only',sha256='0'*64,locator='/example',content='Synthetic test data; not live evidence')])
    response = dict(request_id='synthetic-contract-test',status='abstain',root_cause_hypothesis=None,claims=[],missing_evidence=['Verified claim support'],proposed_patch=[])
    validate_pair(request,response)
    cases = []
    def reject(name, req, res):
        try:
            validate_pair(req,res)
            passed = False
        except (ValueError,TypeError):
            passed = True
        cases.append(dict(case=name,passed=passed))
    altered=deepcopy(response);altered['execution_allowed']=True
    reject('execution_flag',request,altered)
    altered=deepcopy(response);altered['request_id']='wrong'
    reject('request_mismatch',request,altered)
    altered=deepcopy(response);altered['root_cause_hypothesis']='invented'
    reject('abstain_with_diagnosis',request,altered)
    altered=deepcopy(response);altered['claims']=[dict(statement='invented',evidence_ids=['missing'])]
    reject('unknown_reference',request,altered)
    altered=deepcopy(response);altered.update(status='hypothesis',root_cause_hypothesis='unverified',claims=[dict(statement='test',evidence_ids=['synthetic-ref'])])
    reject('bypass_gate',request,altered)
    altered=deepcopy(response);altered['unexpected']='field'
    reject('extra_field',request,altered)
    ready=deepcopy(request);ready['gate'].update(decision='context_ready',answer_supported=True,reasons=[])
    hypothetical=deepcopy(response);hypothetical.update(status='hypothesis',root_cause_hypothesis='Synthetic hypothesis, not a real diagnosis',claims=[dict(statement='Synthetic only',evidence_ids=['synthetic-ref'])],confidence=0.5)
    validate_pair(ready,hypothetical)
    (out/'examples.json').write_text(json.dumps(dict(synthetic=True,request=request,response=response,hypothesis_request=ready,hypothesis_response=hypothetical),indent=2)+'\n')
    summary=dict(passed=all(c['passed'] for c in cases),valid_examples=2,negative_cases=cases,scope='Shape and reference/gate consistency only; no LLM/linter/execution')
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))
    return int(not summary['passed'])

if __name__ == '__main__':
    raise SystemExit(main(Path(sys.argv[1])))
