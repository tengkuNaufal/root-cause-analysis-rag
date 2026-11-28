"""Offline set coverage and artifact provenance; no retrieval/model network calls."""
import unittest
import yaml
from .evaluate_retrieval import build_set,ROOT

class RetrievalSetTests(unittest.TestCase):
    def test_host1_frozen_set_matches_catalog_and_generator(self):
        stored=yaml.safe_load((ROOT/'data/retrieval_host1_testset.yaml').read_text())
        self.assertEqual(stored,build_set())
        self.assertEqual(len(stored['questions']),60)
        self.assertEqual({q['language'] for q in stored['questions']},{'id','en'})
        self.assertEqual(len({q['fault_class'] for q in stored['questions']}),10)
        self.assertTrue(all('ground_truth' not in q and q['question'] for q in stored['questions']))
    def test_runtime_query_uses_observed_keys_not_catalog_labels(self):
        from .retrieval import query_from_facts
        q=query_from_facts([{'type':'setting','key':'neighbor/10.0.35.2/remote_as'}])
        self.assertIn('remote-as',q);self.assertNotIn('10.0.35.2',q);self.assertNotIn('bgp_wrong_remote_as',q)

    def test_pinned_expansion_keeps_source_types_and_hashes(self):
        from .retrieval import _pinned
        import json
        folder=ROOT/'host1/knowledge/supplemental-mtu'
        manifest=json.loads((folder/'manifest.json').read_text())
        doc=_pinned(folder,manifest,'frr-ospf-vty.c',9853,9860)
        self.assertEqual(doc['content_kind'],'frr_source_code')
        self.assertIn('MTU mismatch',doc['content']);self.assertTrue(doc['original_source_sha256'])
        rfc=_pinned(folder,manifest,'rfc2328.txt',4925,4929)
        self.assertIn('Interface MTU',rfc['content'])
        self.assertIn('rejected',rfc['content'])
        check=_pinned(folder,manifest,'frr-ospf-packet.c',1224,1232)
        self.assertIn('ntohs(dd->mtu) > oi->ifp->mtu',check['content'])

    def test_policy_version_present(self):
        from rca.linter import POLICY_VERSION
        self.assertEqual(POLICY_VERSION,'host1-policy-v2')

if __name__=='__main__':unittest.main()
