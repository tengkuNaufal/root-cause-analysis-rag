"""Preserve negative-case artifacts and assess the actual Ollama replay result."""
from copy import deepcopy
import argparse
import json
from pathlib import Path
import sys

from knowledge.evidence import local_path, read
from reasoning_agent.adapter import run

class NoInference:
    def generate(self, payload):
        raise AssertionError('Negative control attempted inference')

def main(directory, positive_name='timer-actual', reuse_controls=False, report_name='summary.json'):
    directory = local_path(directory)
    bundle = read(directory / 'bundle-timers.json')
    question = bundle['question']
    cases = []
    controls = [('unsupported-rca', 'What is the root cause and fix for this MTU mismatch?', 'replay'),
                ('stale-live', question, 'live'), ('corrupt-snapshot', question, 'replay'),
                ('tampered-citation', question, 'replay'),
                ('budget-overflow', question + ' ' * 3000, 'replay')]
    for name, text, mode in controls:
        altered = deepcopy(bundle)
        if name == 'corrupt-snapshot':
            altered['evidence']['inputs']['snapshot']['sha256'] = '0' * 64
        if name == 'tampered-citation':
            altered['documentation'][0]['retrieval']['hits'][0]['text'] += ' invented'
        path = directory / (name + '-input.json')
        if reuse_controls:
            if read(path) != altered:
                raise ValueError('Saved negative control input differs')
            result = read(directory / name / 'audit.json')
            if result['question'] != text or result['mode'] != mode:
                raise ValueError('Saved negative control scope differs')
        else:
            path.write_text(json.dumps(altered))
            result = run(path, directory / name, text, mode, NoInference())
        cases.append(dict(case=name, passed=result['status'] == 'abstain' and not result['model_called'],
                          reason=result.get('reason'), reused=reuse_controls))
    positive = read(local_path(directory / positive_name / 'audit.json'))
    answer = read(local_path(directory / positive_name / 'output-contract.json'))
    passed = bool(positive.get('contract_valid') and positive['model_called'] and
                  answer['status'] == 'hypothesis' and all(c['passed'] for c in cases))
    summary = dict(passed=passed, positive=positive, negative_controls=cases,
                   execution_allowed=False, diagnosis_allowed=False,
                   scope='Actual supported documentation replay plus fail-closed controls; not RCA accuracy')
    report = local_path(directory / report_name)
    if report.exists():
        raise ValueError('Choose a new summary filename')
    report.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return int(not passed)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    p.add_argument('--positive', default='timer-actual')
    p.add_argument('--reuse-controls', action='store_true')
    p.add_argument('--report', default='summary.json')
    args = p.parse_args()
    raise SystemExit(main(args.directory, args.positive, args.reuse_controls, args.report))
