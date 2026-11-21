"""Fresh v2 evaluation frozen before execution; do not reuse as unseen after tuning."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from knowledge.evidence import ROOT, read, ref
from knowledge.retriever import query
from knowledge.quality_gate import assess, citation

CASES = [
 ('timer-order', 'frr', 'In BGP neighbor timers, which argument controls hold time and which controls keepalive?', 'context_ready'),
 ('mss-apply', 'frr', 'Will a new BGP TCP-MSS configuration apply to an existing peer without a hard reset?', 'context_ready'),
 ('path-discovery', 'openconfig', 'What boolean controls path MTU discovery for BGP transport and what is its default?', 'context_ready'),
 ('header-size', 'openconfig', 'Does interface MTU count the frame header, and is the FCS included?', 'abstain'),
 ('fsm-field', 'openconfig', 'Identify the session-state leaf for the BGP FSM and show the ACTIVE enum meaning.', 'context_ready'),
 ('compound-demand', 'frr', 'Explain BGP keepalive and hold timers and describe the temperature for cooking lasagne.', 'abstain'),
 ('unsupported-vendor', 'frr', 'Give a Junos command to repair BGP hold timer expiration.', 'abstain'),
 ('unsupported-mtu', 'frr', 'Diagnose the root cause of an OSPF MTU discrepancy and apply a fix automatically.', 'abstain'),
]

def main(out):
    out.mkdir(parents=True, exist_ok=False)
    files = [ref(ROOT / p) for p in ('host1/knowledge/quality_gate.py','host1/knowledge/question_support.py','host1/knowledge/retriever.py','host1/knowledge/evaluate_preollama.py','host1/knowledge/chunks.jsonl')]
    (out / 'preregistered.json').write_text(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(),cases=CASES,files=files),indent=2))
    base = read(ROOT/'data/host1/evidence-retrieval/replay-final-20261119/L35-down.json')
    rows = []
    for name, platform, question, expected in CASES:
        result = query(question, platform, 5)
        for hit in result['hits']:
            citation(hit, platform)
        bundle = deepcopy(base)
        bundle['documentation'] = [dict(retrieval=result,trigger_evidence=[])]
        gate = assess(bundle, question=question)
        row = dict(case=name, expected=expected, actual=gate['decision'], matches=gate['decision']==expected)
        (out/(name+'.json')).write_text(json.dumps(dict(row=row,retrieval=result,gate=gate),indent=2)+'\n')
        rows.append(row)
        print(json.dumps(row),flush=True)
    summary = dict(cases=rows, matches=sum(r['matches'] for r in rows), unchanged=all(ref(ROOT/r['path'])['sha256']==r['sha256'] for r in files), scope='Fresh assistant-authored v2 query set; not human-blinded benchmark')
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')

if __name__ == '__main__':
    main(Path(sys.argv[1]))
