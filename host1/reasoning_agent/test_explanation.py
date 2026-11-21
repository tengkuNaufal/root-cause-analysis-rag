"""Adversarial citations, causal claims and chronology against real saved evidence."""
from copy import deepcopy
import unittest
from reasoning_agent.explanation import load_run, build, validate_report
from reasoning_agent.evaluate_explanations import CASES

class ExplanationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.loaded={name:load_run(path) for name,path in CASES}
    def selected(self,name='L12-fault'):
        directory,bundle,req,payload,prediction,result,audit=self.loaded[name]
        return directory,req,payload,prediction,build(req,payload,prediction,directory)
    def reject(self,change,name='L12-fault'):
        directory,req,payload,prediction,report=self.selected(name);change(report)
        with self.assertRaises(ValueError):validate_report(report,req,payload,prediction,directory)
    def test_eight_supported_reports(self):
        for name in self.loaded:
            d,r,p,pred,report=self.selected(name)
            self.assertEqual(validate_report(report,r,p,pred,d),report)
    def test_nearest_condition_has_only_own_interface_citation(self):
        for name,target in (('L12-fault','r1:eth1'),('L35-fault','r3:eth4')):
            d,r,p,pred,report=self.selected(name)
            c=next(c for c in report['claims'] if c['key']=='nearest_condition')
            source=next(x for x in p['current']['interfaces'] if x['node']==target)
            self.assertEqual(c['citations'],[source['ref']]);self.assertFalse(c['values']['admin_up'])
    def test_valid_but_wrong_endpoint_id_rejected(self):
        self.reject(lambda r:r['claims'][0].update(citations=['T2']))
    def test_docs_cannot_replace_observation(self):
        self.reject(lambda r:r['claims'][0].update(citations=['D1']))
    def test_invented_id_rejected(self):self.reject(lambda r:r['claims'][0].update(citations=['unknown']))
    def test_admin_up_peer_cannot_be_fault_target(self):
        self.reject(lambda r:next(c for c in r['claims'] if c['key']=='nearest_condition')['values'].update(node='r2:eth1'))
    def test_actor_command_claim_rejected(self):
        self.reject(lambda r:r['claims'][0].update(statement='Operator menjalankan shutdown dan menyebabkan gangguan.'))
    def test_hardware_cause_rejected(self):
        self.reject(lambda r:r.update(root_cause_status='proven_cable_failure'))
    def test_symptom_cannot_be_relabelled_root_cause(self):
        self.reject(lambda r:next(c for c in r['claims'] if c['key']=='physical').update(role='proven_root_cause'))
    def test_generic_doc_is_not_live_knob_proof(self):
        self.reject(lambda r:next(c for c in r['claims'] if c['key']=='mechanism').update(statement='fast-external-failover terbukti aktif.'),'L35-fault')
    def test_old_down_log_cannot_be_current_fault(self):
        self.reject(lambda r:next(c for c in r['claims'] if c['key']=='phase')['values'].update(phase='fault'),'L12-recovered')
    def test_partial_history_cannot_be_recovery(self):
        self.reject(lambda r:next(c for c in r['claims'] if c['key']=='phase')['values'].update(phase='recovered'),'L35-partial')
    def test_history_coverage_needs_audit_ref(self):
        self.reject(lambda r:next(c for c in r['claims'] if c['key']=='phase')['citations'].remove('V1'),'L12-baseline')
    def test_event_time_cannot_be_changed(self):
        self.reject(lambda r:next(c for c in r['claims'] if c['role']=='historical_observation')['values'].update(time='2099-01-01T00:00:00Z'),'L35-recovered')
    def test_source_locator_cannot_be_changed(self):
        self.reject(lambda r:r['citations'][0].update(locator='/wrong'))
    def test_extra_claim_rejected(self):
        self.reject(lambda r:r['claims'].append(dict(key='mtu',statement='MTU mismatch adalah penyebab.')))
    def test_caveat_cannot_be_removed(self):self.reject(lambda r:r.update(limitations=''))
    def test_execution_cannot_be_enabled(self):self.reject(lambda r:r.update(execution_allowed=True))

if __name__=='__main__':unittest.main()
