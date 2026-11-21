"""Preflight/replay six stored cases; expected labels stay outside model inputs."""
import argparse
import json
from knowledge.evidence import ROOT, local_path, read
from reasoning_agent.rca_gate import assess_rca
from reasoning_agent.rca import select, run

STORED = ROOT/'data/host1/evidence-retrieval/replay-final-20261119'
CASES = [(link,phase) for link in ('L12','L35') for phase in ('before','down','restored')]

def main(directory, stage, case=None):
    directory=local_path(directory);directory.mkdir(parents=True,exist_ok=True)
    rows=[]
    for link,phase in CASES:
        name=link+'-'+phase
        if case and case!=name: continue
        source=STORED/(name+'.json')
        if stage=='preflight':
            out=directory/'preflight'/name;out.mkdir(parents=True,exist_ok=False)
            bundle=read(source);gate=assess_rca(bundle)
            (out/'gate.json').write_text(json.dumps(gate,indent=2))
            item=dict(case=name,gate_ready=gate['hypothesis_allowed'],reasons=gate['reasons'])
            if gate['hypothesis_allowed']:
                req,prompt,allowance,view=select(bundle,gate,'preflight','replay')
                (out/'input-contract.json').write_text(json.dumps(req.model_dump(),indent=2))
                (out/'prompt.txt').write_text(prompt)
                (out/'budget.json').write_text(json.dumps(allowance,indent=2))
                item['budget']=allowance;item['passed']=True
            else: item['passed']=False
        else:
            item=read(directory/'actual'/name/'audit.json') if stage=='summarize' else run(source,directory/'actual'/name)
            expected='active_admin_down' if phase=='down' else 'no_current_fault'
            expected_target=('r1:eth1' if link=='L12' else 'r3:eth4') if phase=='down' else None
            item=dict(case=name,actual=item,expected=expected,expected_target=expected_target,
                      passed=item.get('contract_valid') is True and item.get('assessment')==expected and item.get('target')==expected_target)
        rows.append(item);print(json.dumps(item),flush=True)
    report=dict(passed=bool(rows) and all(r['passed'] for r in rows),stage=stage,cases=rows,
                scope='Development replay of known cases; not held-out RCA accuracy or independent trial benchmark')
    label=stage+('-'+case if case else '')+'-summary.json'
    target=directory/label
    if target.exists():raise ValueError('Choose a new run directory or summary label')
    target.write_text(json.dumps(report,indent=2))
    return int(not report['passed'])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory');p.add_argument('--stage',choices=['preflight','actual','summarize'],required=True)
    p.add_argument('--case',choices=[l+'-'+s for l,s in CASES])
    a=p.parse_args();raise SystemExit(main(a.directory,a.stage,a.case))
