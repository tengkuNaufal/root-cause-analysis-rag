"""One-shot unseen-query evaluation; freezes cases and implementation before retrieval."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from knowledge.evidence import ROOT, read, ref
from knowledge.retriever import query
from knowledge.quality_gate import assess, citation

# Written before executing any of these queries. Rule matching is a reference anchor,
# not a human relevance label. Full hits are preserved for separate semantic review.
CASES = [
 ('mtu-en', 'openconfig', 'interface_mtu_definition', 'Which interface field limits the size of a layer two frame, and does its count include the Ethernet header?', r'leaf\s+mtu\s*\{', True, 'context_ready'),
 ('mtu-id', 'openconfig', 'interface_mtu_definition', 'Dalam model interface, apakah batas ukuran frame menghitung header Ethernet? Tunjukkan definisi atributnya.', r'leaf\s+mtu\s*\{', True, 'context_ready'),
 ('state-en', 'openconfig', 'bgp_session_state', 'Where does a monitoring application read the current finite state machine state of a routing peer?', r'leaf\s+session-state\s*\{', True, 'context_ready'),
 ('state-id', 'openconfig', 'bgp_session_state', 'Atribut operasional apa yang menunjukkan tahap mesin status koneksi tetangga BGP saat ini?', r'leaf\s+session-state\s*\{', True, 'context_ready'),
 ('timer-en', 'frr', 'network_context', 'For one BGP peer, how are the interval between keepalive messages and the timeout before declaring the peer dead specified?', r'neighbor\s+PEER\s+timers\s+\(0-65535\)', True, 'context_ready'),
 ('mss-en', 'frr', 'network_context', 'After changing the TCP segment size limit for a BGP neighbor, does the existing session need a hard reset before the setting takes effect?', r'only after hard reset', True, 'context_ready'),
 ('failover-en', 'frr', 'network_context', 'What is the default behavior of a directly attached external BGP session when its physical link flaps?', r'bgp fast-external-failover', True, 'context_ready'),
 ('discovery-en', 'openconfig', 'bgp_mtu_discovery', 'Which BGP transport setting enables path MTU discovery on the neighbor TCP session?', r'leaf\s+mtu-discovery\s*\{', True, 'abstain'),
 ('ospf-fix-gap', 'frr', 'ospf_mtu_remediation', 'OSPF neighbors stay in ExStart after opposite ends use frame sizes of 1500 and 9000. Give a verified FRR command that bypasses this mismatch.', None, False, 'abstain'),
 ('tls-distractor', 'frr', 'network_context', 'Which FRR BGP neighbor command rotates the TLS certificate used for an ordinary eBGP session? Include the certificate renewal interval.', None, False, 'abstain'),
 ('unrelated', 'frr', 'network_context', 'What oven temperature and baking duration make a crisp sourdough pizza?', None, False, 'abstain'),
 ('windows-gap', 'openconfig', 'windows_mtu_remediation', 'Give the PowerShell command that changes the Wi-Fi adapter MTU permanently on Windows 11.', None, False, 'abstain'),
]


def main(output):
    output.mkdir(parents=True, exist_ok=False)
    manifest = dict(frozen_at=datetime.now(timezone.utc).isoformat(), cases=CASES,
        files=[ref(ROOT / p) for p in ('host1/knowledge/evaluate_unseen.py', 'host1/knowledge/retriever.py',
               'host1/knowledge/quality_gate.py', 'host1/knowledge/evidence.py', 'host1/knowledge/chunks.jsonl',
               'host1/knowledge/sources-manifest.json')],
        protocol='New query strings, existing corpus and reused L35-down context. Author knows development set; no independent human labels; no tuning during this evaluation.')
    (output / 'preregistered.json').write_text(json.dumps(manifest, indent=2) + '\n')
    base_path = ROOT / 'data/host1/evidence-retrieval/replay-final-20261119/L35-down.json'
    base = read(base_path)
    rows = []
    for ident, platform, intent, text, pattern, answerable, expected in CASES:
        retrieval = query(text, platform, 5)
        for hit in retrieval['hits']:
            citation(hit, platform)
        bundle = deepcopy(base)
        bundle['documentation'] = [dict(retrieval=retrieval, trigger_evidence=[])]
        gate = assess(bundle, intent)
        ranks = [h['rank'] for h in retrieval['hits'] if pattern and re.search(pattern, h['text'], re.I)]
        row = dict(case=ident, answerable=answerable, reference_anchor_ranks=ranks,
                   gate_expected=expected, gate_actual=gate['decision'], gate_matches=gate['decision'] == expected,
                   accepted=len(gate['accepted_citations']), provenance_verified=len(retrieval['hits']))
        (output / (ident + '.json')).write_text(json.dumps(dict(case=row, query=text,
            intent=intent, anchor_pattern=pattern, input_evidence=ref(base_path), retrieval=retrieval, gate=gate), indent=2) + '\n')
        rows.append(row)
        print(json.dumps(row), flush=True)
    positives = [r for r in rows if r['answerable']]
    summary = dict(completed=True, cases=len(rows), rows=rows,
        anchor_hit_at_5=sum(bool(r['reference_anchor_ranks']) for r in positives) / len(positives),
        anchor_mrr_at_5=sum(1/min(r['reference_anchor_ranks']) if r['reference_anchor_ranks'] else 0 for r in positives)/len(positives),
        task_gate_agreement=sum(r['gate_matches'] for r in rows),
        source_files_unchanged=all(ref(ROOT / r['path'])['sha256'] == r['sha256'] for r in manifest['files']),
        limitations='Anchor metrics are not semantic precision. Task-level gate expectations are stricter than broad network_context v1 contract. No new live faults or Ollama.')
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({k:v for k,v in summary.items() if k != 'rows'}), flush=True)


if __name__ == '__main__':
    main(Path(sys.argv[1]))
