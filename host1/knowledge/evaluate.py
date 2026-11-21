"""Small targeted retrieval acceptance set; not an RCA benchmark."""
import json
from pathlib import Path
import re
import sys

from knowledge.retriever import BASE, query

CASES = [
    ('frr-mtu', 'frr', 'BGP TCP maximum segment size MTU discovery packets exceed link MTU', r'(MTU discovery|Maximum Transmission unit)'),
    ('frr-bgp-timers', 'frr', 'BGP neighbor keepalive holdtime timer expiration configure neighbor timers', r'neighbor\s+PEER\s+timers'),
    ('frr-bgp-link-down', 'frr', 'BGP directly connected eBGP peer link down fast external failover', r'fast-external-failover'),
    ('oc-mtu', 'openconfig', 'interface maximum transmission unit MTU size layer 2 frame leaf mtu', r'leaf\s+mtu\s*\{'),
    ('oc-bgp-timers', 'openconfig', 'BGP neighbor timers hold-time keepalive-interval negotiated hold time', r'leaf\s+(hold-time|keepalive-interval)\s*\{'),
    ('oc-bgp-state', 'openconfig', 'BGP neighbor session-state ESTABLISHED IDLE ACTIVE state', r'leaf\s+session-state\s*\{'),
]


def main(output):
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for ident, platform, text, expected in CASES:
        result = query(text, platform, 5)
        relevant = [h['rank'] for h in result['hits'] if re.search(expected, h['text'], re.I)]
        provenance_ok = True
        for hit in result['hits']:
            m = hit['metadata']
            lines = (BASE / 'sources' / m['filename']).read_text().splitlines()
            expected_text = f"{m['platform']} {m['document_version']} {m['filename']}\n" + '\n'.join(lines[m['line_start']-1:m['line_end']])
            provenance_ok &= hit['text'] == expected_text and m['platform'] == platform
        result.update(test_id=ident, expected_pattern=expected, relevant_ranks=relevant,
                      provenance_ok=provenance_ok, passed=bool(relevant) and provenance_ok)
        (output / (ident + '.json')).write_text(json.dumps(result, indent=2) + '\n')
        rows.append({k: result[k] for k in ('test_id', 'passed', 'relevant_ranks', 'provenance_ok', 'seconds')})
        print(json.dumps(rows[-1]), flush=True)
    probe = query('OSPF adjacency gagal karena MTU kedua interface berbeda', 'frr', 5)
    (output / 'indonesian-probe.json').write_text(json.dumps(probe, indent=2) + '\n')
    ospf_probe = query('OSPF database description packet interface MTU mismatch ip ospf mtu-ignore', 'frr', 5)
    ospf_probe['coverage_note'] = 'Pinned FRR ospfd.rst does not document mtu-ignore; nearest matches must not be represented as verified MTU-mismatch remediation.'
    (output / 'ospf-mtu-coverage-gap.json').write_text(json.dumps(ospf_probe, indent=2) + '\n')
    invalid_rejected = False
    try:
        query('configure MTU', 'cisco', 5)
    except ValueError:
        invalid_rejected = True
    summary = dict(passed=all(r['passed'] for r in rows) and invalid_rejected,
        targeted_cases=rows, unsupported_platform_rejected=invalid_rejected,
        note='Six targeted English queries; term-presence and provenance tests, not broad relevance/diagnosis accuracy. Indonesian probe separate.')
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary), flush=True)
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main(Path(sys.argv[1])))
