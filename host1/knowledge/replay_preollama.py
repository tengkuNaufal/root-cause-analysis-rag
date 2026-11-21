"""Compare stored query hits before/after YANG expansion and gate 2.1."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from knowledge.evidence import ROOT, read
from knowledge.yang_context import expand
from knowledge.quality_gate import assess, citation

def main(out):
    out.mkdir(parents=True, exist_ok=False)
    rows = []
    paths = list((ROOT/'data/host1/pre-ollama/fresh-v2').glob('*.json'))
    paths += [ROOT/'data/host1/retrieval-unseen/run-20261119'/f'{name}.json' for name in ('state-en','state-id')]
    for path in paths:
        old = read(path)
        if 'retrieval' not in old:
            continue
        result = deepcopy(old['retrieval'])
        result['hits'] = [expand(h) for h in result['hits']]
        for h in result['hits']:
            citation(h, result['platform_filter'])
        bundle = read(ROOT/'data/host1/evidence-retrieval/replay-final-20261119/L35-down.json')
        bundle['documentation'] = [dict(retrieval=result)]
        gate = assess(bundle, question=result['query'])
        expected = old['row']['expected'] if 'row' in old else ('context_ready' if path.stem == 'state-en' else 'abstain')
        row = dict(case=path.stem, before=old['gate']['decision'], after=gate['decision'], expected=expected, passed=gate['decision']==expected,
                   expanded=sum('context_expansion' in h for h in result['hits']))
        (out/path.name).write_text(json.dumps(dict(row=row,retrieval=result,gate=gate),indent=2)+'\n')
        rows.append(row)
    (out/'summary.json').write_text(json.dumps(dict(passed=all(r['passed'] for r in rows),rows=rows,scope='Post-change regression on disclosed cases; not held-out'),indent=2)+'\n')
    print(json.dumps(rows,indent=2))

if __name__ == '__main__':
    main(Path(sys.argv[1]))
