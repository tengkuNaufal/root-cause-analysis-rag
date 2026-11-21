"""Focused regression for the new audit harness; production remains frozen."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from mtu_variations import resolve_pointer
from audit_mtu_variations import check_numeric_claim

class VariationAuditTests(unittest.TestCase):
    def test_snapshot_array_pointer(self):
        document={'routers':{'r1':{'sources':{'interfaces':{'data':[{'mtu':9000}]}}}}}
        self.assertEqual(resolve_pointer(document,'/routers/r1/sources/interfaces/data/0'),{'mtu':9000})
    def test_nested_arrays(self):self.assertEqual(resolve_pointer({'x':[[1280,9216]]},'/x/0/1'),9216)
    def test_escaped_keys(self):self.assertEqual(resolve_pointer({'a/b':{'~x':[1492]}},'/a~1b/~0x/0'),1492)
    def test_array_indices_fail_closed(self):
        for key in ('-1','1','00','-','not_an_index'):
            with self.assertRaises((ValueError,IndexError)):resolve_pointer({'x':[1500]},'/x/'+key)
    def sample(self):
        return dict(statement='2026-11-19T10:00:00Z: r1:eth1 MTU=1492, admin UP/carrier UP.',evidence_ids=['T1']),{
            'T1':dict(kind='telemetry',content='{"node":"r1:eth1","mtu":1492}'),
            'T2':dict(kind='telemetry',content='{"node":"r2:eth1","mtu":1492}'),
            'D1':dict(kind='documentation',content='Definition only')}
    def test_correct_numeric_claim(self):
        claim,refs=self.sample();check_numeric_claim(claim,refs)
    def test_valid_id_wrong_endpoint_rejected_even_with_equal_mtu(self):
        claim,refs=self.sample();claim['evidence_ids']=['T2']
        with self.assertRaises(ValueError):check_numeric_claim(claim,refs)
    def test_documentation_not_live_evidence(self):
        claim,refs=self.sample();claim['evidence_ids']=['D1']
        with self.assertRaises(ValueError):check_numeric_claim(claim,refs)
    def test_wrong_numeric_value_rejected(self):
        claim,refs=self.sample();claim['statement']=claim['statement'].replace('1492','9000')
        with self.assertRaises(ValueError):check_numeric_claim(claim,refs)
    def test_non_atomic_numeric_claim_rejected(self):
        claim,refs=self.sample();claim['evidence_ids']=['T1','T2']
        with self.assertRaises(ValueError):check_numeric_claim(claim,refs)

if __name__=='__main__':unittest.main()
