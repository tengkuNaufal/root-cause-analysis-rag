"""Post-run independent contract, raw-value and frozen-evidence audit; no inference."""
import json
import sys
from knowledge.evidence import read, local_path, verify
from agent_contract.models import Response, validate_pair
from reasoning_agent.evaluate_negative import fingerprints, save
from reasoning_agent.temporal import validate_endpoint, validate_observations

def main(directory):
    directory=local_path(directory);registered=read(directory/'preregistered.json')
    assert fingerprints()==registered['code'],'Implementation changed'
    verify(registered['cases']['path'],registered['cases']['sha256'])
    for path,sha in registered['sources'].items():verify(path,sha)
    summary=read(directory/'evaluation/summary.json');rows=[]
    for case in read(directory/'cases.json'):
        verify(case['bundle']['path'],case['bundle']['sha256'])
        path=directory/'evaluation'/case['id'];response=read(path/'output-contract.json')
        Response.model_validate(response)
        assert response['execution_allowed'] is False and response['proposed_patch']==[]
        audit=read(path/'audit.json')
        if case['expected']=='abstain':
            assert audit['model_called'] is False and audit['llm_requests']==0
            assert response['status']=='abstain'
        else:
            request=read(path/'input-contract.json');validate_pair(request,response)
            payload=read(path/'visible-evidence.json')
            records=read(path/'endpoint-bindings.json')
            assert len(records)==2
            for index,(record,source) in enumerate(zip(records,payload['current']['interfaces']),1):
                assert record['node']==source['node'] and record['citation']==source['ref']
                raw=read(path/f'endpoint-{index}-response.json')
                value=json.loads(raw['response']);assert value==record['model_values']
                validate_endpoint(value,source)
            validate_observations(read(path/'raw-observations.json'),payload)
            raw=json.loads(read(path/'ollama-response.json')['response'])
            assert raw==read(path/'raw-phase.json')=={'phase':'undetermined'}
            assert payload['history']['complete'] is False
            assert audit['facts_validated'] and audit['contract_valid']
        rows.append(dict(id=case['id'],audit_passed=True))
    assert summary['passed']==len(rows)
    target=directory/'post-audit.json'
    if target.exists():raise ValueError('Preserve earlier audit')
    save(target,dict(passed=True,total=len(rows),code_unchanged=True,source_bundles_unchanged=True,
        note='Gate abstention is controller behavior; six raw undetermined phases are actual model output.',cases=rows))
    print(json.dumps(dict(passed=True,total=len(rows))))

if __name__=='__main__':main(sys.argv[1])
