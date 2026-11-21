"""Regression on now-disclosed queries; keeps v1 results intact."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from knowledge.evidence import ROOT, read, ref
from knowledge.quality_gate import assess

def main(out):
    out.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'data/host1/retrieval-unseen/run-20261119'
    base = read(ROOT / 'data/host1/evidence-retrieval/replay-final-20261119/L35-down.json')
    rows = []
    for name in ('mtu-en','mtu-id','state-en','state-id','timer-en','mss-en','failover-en','discovery-en','ospf-fix-gap','tls-distractor','unrelated','windows-gap'):
        old = read(source / (name + '.json'))
        bundle = deepcopy(base)
        bundle['documentation'] = [dict(retrieval=old['retrieval'], trigger_evidence=[])]
        result = assess(bundle, old['intent'])
        expected = 'context_ready' if name in ('timer-en','mss-en','failover-en','discovery-en') else 'abstain'
        row = dict(case=name, v1=old['gate']['decision'], v2=result['decision'], expected=expected,
                   passed=result['decision'] == expected and not result['execution_allowed'] and not result['diagnosis_allowed'], reasons=result['reasons'])
        (out / (name + '.json')).write_text(json.dumps(dict(input=ref(source / (name + '.json')), comparison=row, gate=result), indent=2)+'\n')
        rows.append(row)
    (out / 'summary.json').write_text(json.dumps(dict(passed=all(r['passed'] for r in rows), cases=rows,
        scope='Development regression after disclosure; expected outcomes based on missing/full claim support, not original anchor expectations'), indent=2)+'\n')
    print(json.dumps(rows, indent=2))
    return int(not all(r['passed'] for r in rows))

if __name__ == '__main__':
    raise SystemExit(main(Path(sys.argv[1])))
