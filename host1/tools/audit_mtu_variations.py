"""Verify real presentation reversal, source bindings and bounded citation negatives."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from knowledge.evidence import ROOT, read, ref, verify, local_path
from reasoning_agent.mtu import save
from agent_contract.models import validate_pair
from mtu_variations import check_code, BASE

def check_numeric_claim(claim,refs):
    if len(claim['evidence_ids'])!=1:raise ValueError('Not atomic')
    r=refs[claim['evidence_ids'][0]]
    if r['kind']!='telemetry':raise ValueError('Wrong evidence kind')
    row=json.loads(r['content'])
    # Value/node are bound to the source ref; exact template prefix carries time.
    suffix=f': {row["node"]} MTU={row["mtu"]}, admin UP/carrier UP.'
    if not claim['statement'].endswith(suffix):raise ValueError('Wrong endpoint/value citation')

def main(directory,post=False):
    directory=local_path(directory);check_code(directory);reg=read(directory/'preregistered.json')
    for e in (reg['cases'],reg['expected'],reg['harness']):verify(e['path'],e['sha256'])
    for p,sha in {**reg['files'],**reg['originals']}.items():verify(p,sha)
    cases=read(directory/'cases.json');expected=read(directory/'expected.json');counts={};seen={};negatives=[]
    for case in cases:
        if expected[case['id']]['phase']=='abstain':continue
        link=case['link'];source=read(BASE/link/'0/bundle.json')['evidence']
        native=[n['router']+':'+n['name'] for n in source['interfaces']]
        wanted_order=native[::-1] if case['reverse'] else native
        seq=read(verify(case['sequence']['path'],case['sequence']['sha256']))
        for entry,values in zip(seq['snapshots'],expected[case['id']]['node_values']):
            e=read(verify(entry['path'],entry['sha256']))['evidence']
            order=[n['router']+':'+n['name'] for n in e['interfaces']]
            if order!=wanted_order:raise ValueError('Fixture endpoint order is not the declared order')
            if {n['router']+':'+n['name']:n['observed']['mtu'] for n in e['interfaces']}!=values:
                raise ValueError('Fixture values differ from intended node assignment')
            if any(x['state']!='up' for x in e['physical']):raise ValueError('Unexpected physical failure')
            if any(not (s['state'].startswith('Full') if e['focus']['protocol']=='ospf' else s['state']=='Established') for s in e['sessions']):
                raise ValueError('Peers not healthy in no-routing-impact fixtures')
        counts[str((case['reverse'],case.get('swapped')))]=counts.get(str((case['reverse'],case.get('swapped'))),0)+1
        seen.setdefault(link,set()).add(tuple(wanted_order))
        if post:
            path=directory/'evaluation'/case['id'];request=read(path/'input-contract.json');response=read(path/'output-contract.json')
            validate_pair(request,response);refs={r['id']:r for r in request['evidence']}
            if response['status']!='hypothesis':continue
            numeric=[c for c in response['claims'] if ' MTU=' in c['statement']]
            for claim in numeric:check_numeric_claim(claim,refs)
            if not negatives and numeric:
                claim=numeric[0];wrong=deepcopy(claim)
                wrong['evidence_ids']=['S1T2'] if claim['evidence_ids']==['S1T1'] else ['S1T1']
                document=deepcopy(claim);document['evidence_ids']=['D1']
                for label,counterfeit in (('valid_id_wrong_endpoint',wrong),('documentation_for_live_value',document)):
                    altered=deepcopy(response);altered['claims'][0]=counterfeit
                    validate_pair(request,altered)  # IDs exist: contract validity alone is insufficient.
                    try:check_numeric_claim(counterfeit,refs)
                    except ValueError as exc:rejected=True;reason=str(exc)
                    else:rejected=False;reason=None
                    if not rejected:raise ValueError('Counterfeit citation accepted by numeric audit')
                    negatives.append(dict(case=case['id'],kind=label,copy=counterfeit,contract_ids_valid=True,
                        numeric_audit_rejected=rejected,reason=reason,original_response=ref(path/'output-contract.json')))
    if any(len(v)!=2 for v in seen.values()):raise ValueError('Both actual endpoint orders were not exercised')
    result=dict(passed=True,production_unchanged=True,originals_unchanged=True,fixtures_unchanged=True,
        positive_layouts=sum(counts.values()),actual_orders={k:[list(x) for x in sorted(v)] for k,v in seen.items()},
        no_routing_effect_simulated=True,citation_counterfeit_copies=negatives,
        auditor=ref(Path(__file__)),note='Numeric source/template check only, not general free-prose entailment')
    if post:
        summary=read(directory/'evaluation/summary.json');result['accepted_count']=summary['passed'];result['total']=summary['total']
        result['unique_model_requests']=summary['unique_model_requests']
    target=directory/('post-audit.json' if post else 'preflight-audit.json')
    if target.exists():raise ValueError('Preserve prior audit')
    save(target,result);print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory');p.add_argument('--post',action='store_true');a=p.parse_args()
    main(a.directory,a.post)
