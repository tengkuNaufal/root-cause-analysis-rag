"""Fail-closed integration checks against frozen real evidence; no model calls."""
from copy import deepcopy
import json
import tempfile
from pathlib import Path
import unittest

from knowledge.evidence import ROOT, read
from knowledge.quality_gate import assess
from reasoning_agent.adapter import budget, run, selected_request, validate_response, draft_to_contract

QUESTION = 'Which BGP timer value is keepalive and which is hold time?'

def fixture():
    bundle = read(ROOT / 'data/host1/evidence-retrieval/replay-final-20261119/L35-down.json')
    retrieval = read(ROOT / 'data/host1/retrieval-unseen/run-20261119/timer-en.json')['retrieval']
    bundle['documentation'] = [dict(retrieval=retrieval)]
    bundle['question'] = QUESTION
    return bundle

class NeverCall:
    def generate(self, payload):
        raise AssertionError('Gate must prevent inference')

class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.bundle = fixture()
        self.gate = assess(self.bundle, question=QUESTION)

    def selected(self, question=QUESTION):
        return selected_request(self.bundle, question, 'replay', self.gate, 'r-test')

    def response(self, req):
        return dict(done=True, done_reason='stop', prompt_eval_count=100, eval_count=100,
                    response=json.dumps(dict(request_id=req.request_id, status='hypothesis',
                    root_cause_hypothesis='A bounded documentation explanation, not a diagnosis.',
                    confidence=None, claims=[dict(statement='First keepalive, second hold time.', evidence_ids=['E1'])],
                    missing_evidence=[], proposed_patch=[], execution_allowed=False)))

    def test_selected_claims_gate_and_budget(self):
        req, prompt, allowance, gate = self.selected()
        self.assertTrue(gate['answer_supported'])
        self.assertLessEqual(allowance['prompt_upper_bound'] + 512 + 64, 2048)
        self.assertEqual({r.kind for r in req.evidence}, {'documentation','telemetry','graph','log'})
        self.assertTrue(all(r.sha256 and r.locator for r in req.evidence))
        self.assertIn('.. clicmd:: neighbor PEER timers', req.evidence[0].content)
        self.assertNotIn('source_path', prompt)  # Full provenance is retained outside token budget.

    def test_contract_accepts_cited_bounded_reply(self):
        req, _, allowance, _ = self.selected()
        self.assertEqual(validate_response(req, self.response(req), allowance)['status'], 'hypothesis')

    def test_draft_maps_answer_verbatim_with_controller_flags(self):
        req, _, _, _ = self.selected()
        text = 'The first argument is keepalive; the second is hold time.'
        result = draft_to_contract(req, dict(answer=text, evidence_ids=['E1'], missing_evidence=[]))
        self.assertEqual(result['root_cause_hypothesis'], text)
        self.assertEqual(result['claims'][0]['statement'], text)
        self.assertEqual(result['request_id'], req.request_id)
        self.assertEqual(result['proposed_patch'], [])
        self.assertIs(result['execution_allowed'], False)

    def test_draft_cannot_set_execution_flag(self):
        req, _, _, _ = self.selected()
        with self.assertRaises(ValueError):
            draft_to_contract(req, dict(answer='text', evidence_ids=['E1'], missing_evidence=[], execution_allowed=True))

    def test_draft_cannot_cite_telemetry_for_definition(self):
        req, _, _, _ = self.selected()
        with self.assertRaises(ValueError):
            draft_to_contract(req, dict(answer='text', evidence_ids=['E2'], missing_evidence=[]))

    def test_draft_abstention_requires_reason(self):
        req, _, _, _ = self.selected()
        with self.assertRaises(ValueError):
            draft_to_contract(req, dict(answer=None, evidence_ids=[], missing_evidence=[]))

    def test_unknown_reference_rejected(self):
        self.reject_response(lambda r: r['claims'][0].update(evidence_ids=['invented']))

    def test_null_hypothesis_rejected(self):
        self.reject_response(lambda r: r.update(root_cause_hypothesis=None))

    def test_irrelevant_telemetry_citation_mixed_with_document_rejected(self):
        self.reject_response(lambda r: r['claims'][0].update(evidence_ids=['E1','E2']))

    def test_uncited_claim_rejected(self):
        self.reject_response(lambda r: r['claims'][0].update(evidence_ids=['E2']))

    def test_request_id_mismatch_rejected(self):
        self.reject_response(lambda r: r.update(request_id='another-request'))

    def test_execution_flag_rejected(self):
        self.reject_response(lambda r: r.update(execution_allowed=True))

    def test_extra_fields_rejected(self):
        self.reject_response(lambda r: r.update(run_now=True))

    def test_patch_rejected_even_when_contract_shape_valid(self):
        self.reject_response(lambda r: r.update(proposed_patch=[dict(router='r3',interface='eth4',
            interpreter='linux_argv',arguments=['ip','link','set','eth4','up'],
            evidence_ids=['E1'],rationale='Synthetic rejected proposal',validation_status='unvalidated')]))

    def reject_response(self, change):
        req, _, allowance, _ = self.selected()
        raw = self.response(req)
        payload = json.loads(raw['response']); change(payload)
        raw['response'] = json.dumps(payload)
        with self.assertRaises((ValueError, TypeError)):
            validate_response(req, raw, allowance)

    def test_truncated_generation_rejected(self):
        req, _, allowance, _ = self.selected()
        raw = self.response(req); raw['done_reason'] = 'length'
        with self.assertRaises(ValueError):
            validate_response(req, raw, allowance)

    def test_unexpected_token_count_rejected(self):
        req, _, allowance, _ = self.selected()
        raw = self.response(req); raw['prompt_eval_count'] = 9999
        with self.assertRaises(ValueError):
            validate_response(req, raw, allowance)

    def test_oversized_context_rejected_without_truncation(self):
        with self.assertRaisesRegex(ValueError, 'context_budget_exceeded'):
            self.selected(QUESTION + ' ' * 3000)

    def test_control_token_injection_rejected(self):
        with self.assertRaisesRegex(ValueError, 'reserved_model_control_marker'):
            self.selected(QUESTION + ' <|eot_id|>')

    def blocked(self, bundle, question=QUESTION, mode='replay'):
        with tempfile.TemporaryDirectory(dir=ROOT / 'data/host1') as directory:
            source = Path(directory) / 'bundle.json'; source.write_text(json.dumps(bundle))
            audit = run(source, Path(directory) / 'out', question, mode, NeverCall())
            self.assertFalse(audit['model_called'])
            self.assertEqual(audit['status'], 'abstain')
            result = read(Path(directory) / 'out/output-contract.json')
            self.assertEqual(result['proposed_patch'], [])
            self.assertIs(result['execution_allowed'], False)
            return audit

    def test_corrupt_source_hash_stops_before_inference(self):
        self.bundle['evidence']['inputs']['snapshot']['sha256'] = '0' * 64
        self.assertIn('invalid_evidence', self.blocked(self.bundle)['reason'])

    def test_tampered_document_stops_before_inference(self):
        self.bundle['documentation'][0]['retrieval']['hits'][0]['text'] += 'invented'
        self.assertIn('invalid_document_citation', self.blocked(self.bundle)['reason'])

    def test_stale_live_evidence_stops_before_inference(self):
        self.assertIn('stale_or_future_snapshot', self.blocked(self.bundle, mode='live')['reason'])

    def test_root_cause_request_stops_before_inference(self):
        self.assertIn('unsupported_question_scope', self.blocked(self.bundle, question='What is the root cause and fix?')['reason'])

if __name__ == '__main__':
    unittest.main()
