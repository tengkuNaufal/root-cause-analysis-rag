import unittest
from copy import deepcopy
from knowledge.evidence import ROOT, read
from knowledge.quality_gate import assess
from knowledge.question_support import requirements

class QuestionTests(unittest.TestCase):
    def bundle(self):
        b = read(ROOT/'data/host1/evidence-retrieval/replay-final-20261119/L35-down.json')
        r = read(ROOT/'data/host1/retrieval-unseen/run-20261119/timer-en.json')['retrieval']
        b['documentation'] = [dict(retrieval=r)]
        return b

    def test_explicit_question_overrides_favorable_retrieval_query(self):
        self.assertEqual(assess(self.bundle(), question='How do I bake a pizza?')['decision'], 'abstain')

    def test_question_cannot_bypass_hash(self):
        b = self.bundle()
        b['evidence']['inputs']['snapshot']['sha256'] = 'bad'
        self.assertEqual(assess(b)['decision'], 'abstain')

    def test_trigger_metadata_cannot_hide_arbitrary_query(self):
        b = self.bundle()
        b['documentation'][0]['trigger_evidence'] = [b['evidence']['inputs']['snapshot']]
        b['documentation'][0]['retrieval']['query'] = 'What oven temperature bakes pizza?'
        self.assertEqual(assess(b)['decision'], 'abstain')

    def test_header_is_separate_requirement(self):
        self.assertEqual(len(requirements('Does the interface MTU include the Ethernet header?')), 2)

    def test_compound_unsupported_request(self):
        self.assertIsNone(requirements('What are BGP keepalive and hold timers and also how to bake pizza?'))

    def test_freshness_still_required(self):
        self.assertEqual(assess(self.bundle(), mode='live', as_of='2099-01-01T00:00:00Z')['decision'], 'abstain')

    def test_no_evidence_does_not_become_answer(self):
        self.assertFalse(assess({}, question='BGP keepalive and hold timers?')['answer_supported'])

if __name__ == '__main__':
    unittest.main()
