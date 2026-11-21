from copy import deepcopy
import unittest
from knowledge.evidence import ROOT, read
from knowledge.yang_context import expand, leaf_spans
from knowledge.quality_gate import citation, assess
from knowledge.question_support import requirements

class YangTests(unittest.TestCase):
    def test_braces_in_description_and_comments(self):
        self.assertEqual(leaf_spans('leaf a {\n description "}"; // {\n}\n'), [(1,3)])

    def test_state_declaration_expanded_with_provenance(self):
        hit = read(ROOT/'data/host1/retrieval-unseen/run-20261119/state-en.json')['retrieval']['hits'][0]
        new = expand(hit)
        self.assertIn('leaf session-state', new['text'])
        self.assertEqual(new['retrieval_anchor']['id'], hit['id'])
        self.assertEqual(new['rank'], hit['rank'])
        citation(new, 'openconfig')

    def test_size_bound(self):
        hit = read(ROOT/'data/host1/retrieval-unseen/run-20261119/state-en.json')['retrieval']['hits'][0]
        self.assertEqual(expand(hit, max_lines=1), hit)

    def test_new_compound_rejected(self):
        self.assertIsNone(requirements('Explain BGP keepalive and hold timers and describe the temperature for cooking lasagne.'))

    def test_default_requires_separate_claim(self):
        self.assertEqual(len(requirements('What boolean controls path MTU discovery for BGP transport and what is its default?')), 2)

if __name__ == '__main__':
    unittest.main()
