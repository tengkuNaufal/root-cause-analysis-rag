"""Revalidate completed runs and explain verified findings with explicit source origins."""
import argparse
import hashlib
import json
from agent_contract.models import Request, validate_pair
from knowledge.evidence import local_path, read
from reasoning_agent.rca_gate import assess_rca
from reasoning_agent.rca import select, validate_draft, observed_healthy
from reasoning_agent.replay_rca import CASES

def explain(bundle,req,audit,result,view):
    e=bundle['evidence']
    if audit['assessment']=='active_admin_down':
        node=next(n for n in e['interfaces'] if n['router']+':'+n['name']==audit['target'])
        if node['observed']['admin_up'] is not False:
            raise ValueError('Cannot explain unobserved administrative-down condition')
        text=('Operational hypothesis: '+audit['target']+' is administratively DOWN [T1,T2]. '
              'The peer loses carrier while the physical graph is DOWN [T1,T2,G1]. '
              +e['focus']['protocol'].upper()+' peer states are '+','.join(s['state'] for s in e['sessions'])+
              ' [G1], with a matching peer-specific transition log [L1]. '
              'The documented link-down mechanism supports this interpretation [D1]. '
              'The initiator and original command are not observed.')
        chain=[dict(role='observed_local_condition',target=audit['target'],admin_up=False,citations=['T1','T2']),
               dict(role='physical_effect',state=e['physical'][0]['state'],citations=['T1','T2','G1']),
               dict(role='protocol_effect',protocol=e['focus']['protocol'],states=[s['state'] for s in e['sessions']],citations=['G1','L1']),
               dict(role='documented_mechanism',citation='D1',semantics='mechanism_support_not_proof_of_live_configuration_or_initiator')]
    else:
        text=('No current fault is observed on the focus link: both endpoints are admin/carrier UP '
              'and both '+e['focus']['protocol'].upper()+' peers are healthy [T1,T2,G1]. '
              'Historical DOWN logs alone do not establish a current fault.')
        chain=[dict(role='current_observations',physical=e['physical'][0]['state'],
                    states=[s['state'] for s in e['sessions']],citations=['T1','T2','G1'])]
    return dict(assessment=audit['assessment'],target=audit['target'],finding_origin=audit['analysis_origin'],
        explanation_origin='controller_alignment_of_verified_observations_and_validated_finding',
        explanation=text,causal_chain=chain,
        original_contract_hypothesis=result['root_cause_hypothesis'],
        model_text_preserved=True,model_called=audit['model_called'],
        evidence_view=view,
        citations=[dict(id=r.id,kind=r.kind,path=r.source_path,sha256=r.sha256,locator=r.locator) for r in req.evidence],
        limitations=['Operational hypothesis, not proof of initiator or underlying hardware fault.',
                     'Snapshots are non-atomic; temporal correlation is not general causal entailment.',
                     'Controller explanation is separate from the original model text; LLM prose quality is not scored.',
                     'Healthy findings are rules, not successful LLM diagnoses.'],
        diagnosis_allowed=False,execution_allowed=False,proposed_patch=[])

def main(directory):
    directory=local_path(directory);destination=directory/'review'
    destination.mkdir(exist_ok=False)
    rows=[]
    for link,phase in CASES:
        name=link+'-'+phase;run=directory/'actual'/name
        audit=read(run/'audit.json');path=local_path(audit['bundle']['path'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=audit['bundle']['sha256']:
            raise ValueError('Input bundle changed after inference')
        bundle=read(path);gate=assess_rca(bundle,audit['mode'])
        if not gate['hypothesis_allowed']:raise ValueError('Review gate abstains')
        req=Request.model_validate(read(run/'input-contract.json'))
        rebuilt,prompt,allowance,view=select(bundle,gate,req.request_id,audit['mode'])
        if rebuilt!=req:raise ValueError('Selected input no longer matches sources')
        if audit['model_called']:
            draft,expected=validate_draft(req,read(run/'ollama-response.json'),allowance,bundle['evidence'])
            if draft.assessment!=audit['assessment'] or draft.target!=audit['target']:
                raise ValueError('Audit differs from validated draft')
        else:
            expected=observed_healthy(req,bundle['evidence'])
            if audit['assessment']!='no_current_fault' or audit['target'] is not None:
                raise ValueError('Rule audit disagrees with observed healthy state')
        result=validate_pair(req.model_dump(),read(run/'output-contract.json')).model_dump()
        if result!=expected:raise ValueError('Saved contract differs from validated output')
        report=explain(bundle,req,audit,result,view)
        (destination/(name+'.json')).write_text(json.dumps(report,indent=2))
        rows.append(dict(case=name,assessment=report['assessment'],target=report['target'],origin=report['finding_origin']))
    summary=dict(passed=True,cases=rows,scope='Revalidated evidence alignment, not an independent semantic review')
    (destination/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory')
    main(p.parse_args().directory)
