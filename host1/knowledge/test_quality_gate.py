import unittest
from copy import deepcopy
from knowledge.evidence import ROOT, read, retrieve_bundle
from knowledge.quality_gate import assess, relevant


class GateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = read(ROOT / 'data/host1/evidence-retrieval/replay-final-20261119/L35-down.json')

    def test_invalid_mode(self):
        self.assertEqual(assess(self.bundle, mode='guess')['decision'], 'abstain')

    def test_invalid_age(self):
        self.assertEqual(assess(self.bundle, max_age_seconds=0)['decision'], 'abstain')

    def test_missing_evidence(self):
        self.assertEqual(assess({})['decision'], 'abstain')

    def test_score_cannot_override_topic(self):
        b = deepcopy(self.bundle)
        b['documentation'] = [d for d in b['documentation'] if d['retrieval']['platform_filter'] == 'openconfig']
        for group in b['documentation']:
            for hit in group['retrieval']['hits']:
                hit.update(cosine_distance=0, rrf_score=1000000)
        self.assertEqual(assess(b)['decision'], 'abstain')

    def test_metadata_prefix_not_topic_evidence(self):
        hit = dict(text='frr bgp neighbor session\nUnrelated storage documentation',
                   metadata=dict(platform='frr', content_kind='cli_documentation'))
        self.assertFalse(relevant(hit, 'network_context', 'bgp')[0])

    def test_existing_gate_cannot_bypass(self):
        b = deepcopy(self.bundle)
        b.update(documentation=[], quality_gate=dict(decision='context_ready'))
        self.assertEqual(assess(b)['decision'], 'abstain')

    def test_builder_attaches_gate_and_free_question_abstains(self):
        queries = {d['retrieval']['query']: d['retrieval'] for d in self.bundle['documentation']}
        def stored_query(text, platform, count):
            return deepcopy(queries.get(text, dict(query=text, platform_filter=platform, hits=[])))
        inputs = self.bundle['evidence']['inputs']
        args = [inputs['graph']['path'], inputs['inventory']['path'], 'L35']
        generated = retrieve_bundle(*args, query_fn=stored_query)
        self.assertEqual(generated['quality_gate']['decision'], 'context_ready')
        generated = retrieve_bundle(*args, question='Fix the root cause now', query_fn=stored_query)
        self.assertEqual(generated['quality_gate']['decision'], 'abstain')
        self.assertIsNone(generated['executable_patch'])


if __name__ == '__main__':
    unittest.main()
