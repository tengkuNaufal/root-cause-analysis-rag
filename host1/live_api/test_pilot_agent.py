"""Synthetic semantic regressions for every supported class. No catalog/model/lab operations."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from .agent import DiagnosisDraft, DiagnosisEngine, DiagnosisError, NAMED_SYSTEM, decision_to_draft
from .capture import write
from .repair_policy import validate_repair, RepairError
from .settings import parse, differences
from .test_agent import FixtureCapture, run_engine


def setting(key,expected,observed,router='r1'):
    f=dict(type='setting',key=key,expected=expected,observed=observed,router=router,anomaly=True)
    if key.startswith(('neighbor/','bgp/','route_map/','prefix_list/')):
        f['configuration_context']={'expected_bgp_asn':65001}
    if key.startswith(('route_map/','prefix_list/')):
        f['policy_direction']='inbound';f['configuration_context']['baseline_policy_entries']=[]
    return f


def physical(mtu=1500,up=True):
    return dict(type='physical',link='synthetic',expected_mtu=1500,anomaly=True,endpoints=[
        dict(router='r1',interface='eth1',observed=dict(mtu=mtu,admin_up=up)),
        dict(router='r2',interface='eth1',observed=dict(mtu=1500,admin_up=True))])


def cases():
    # Values are synthetic observations, independent of fault IDs or benchmark order.
    return [
        ('mtu_mismatch',[physical(1400)],'ip',['link','set','dev','eth1','mtu','1500']),
        ('link_down',[physical(up=False)],'ip',['link','set','dev','eth1','up']),
        ('wrong_ip_address',[setting('interface/eth1/addresses',['10.0.12.1/30'],['10.0.212.1/30'])],
         'vtysh',['configure terminal','interface eth1','no ip address 10.0.212.1/30','ip address 10.0.12.1/30']),
        ('ospf_hello_mismatch',[setting('interface/eth1/ospf_hello',1,40)],
         'vtysh',['configure terminal','interface eth1','ip ospf hello-interval 1']),
        ('ospf_area_mismatch',[setting('interface/eth1/ospf_area','0.0.0.0','0.0.0.1')],
         'vtysh',['configure terminal','interface eth1','no ip ospf area 0.0.0.1','ip ospf area 0']),
        ('ospf_auth_mismatch',[setting('interface/eth1/ospf_authentication',None,'message-digest'),
            setting('interface/eth1/ospf_key_present',False,True),setting('interface/eth1/ospf_key_ids',[],[7])],
         'vtysh',['configure terminal','interface eth1','no ip ospf message-digest-key 7','no ip ospf authentication']),
        ('bgp_neighbor_shutdown',[setting('neighbor/10.255.0.2/shutdown',False,True)],
         'vtysh',['configure terminal','router bgp 65001','no neighbor 10.255.0.2 shutdown']),
        ('bgp_wrong_remote_as',[setting('neighbor/10.255.0.2/remote_as',65001,65101)],
         'vtysh',['configure terminal','router bgp 65001','neighbor 10.255.0.2 remote-as 65001']),
        ('bgp_missing_network',[setting('bgp/networks',['10.100.1.1/32'],None)],
         'vtysh',['configure terminal','router bgp 65001','address-family ipv4 unicast','network 10.100.1.1/32']),
        ('bgp_inbound_filter',[setting('route_map/IMPORT/deny/5',None,['match ip address prefix-list TEMP']),
            setting('prefix_list/TEMP/seq/5',None,'permit 10.100.5.1/32')],
         'vtysh',['configure terminal','no route-map IMPORT deny 5','no ip prefix-list TEMP']),
    ]


def draft(cause,tool,args):
    return DiagnosisDraft.model_validate(decision_to_draft(dict(root_cause_class=cause,
        root_cause_router='r1',confidence=.8,explanation='Synthetic measured deviation.',evidence_ids=['e1'],
        commands=[dict(router='r1',interpreter=tool,args=args)])))


class PilotAgentTests(unittest.TestCase):
    def test_expected_repairs_for_all_ten_classes_pass_without_rewriting(self):
        for cause,facts,tool,args in cases():
            with self.subTest(cause=cause):
                result=draft(cause,tool,args);before=result.model_dump()
                validate_repair({'facts':{'observations':facts}},result)
                self.assertEqual(before,result.model_dump())
                self.assertIn(cause,NAMED_SYSTEM)

    def test_area_change_requires_removal_before_replacement(self):
        cause,facts,tool,args=next(c for c in cases() if c[0]=='ospf_area_mismatch')
        bad=[args[:2]+[args[-1]],args[:2]+list(reversed(args[-2:])),args+['no ip ospf area 0']]
        for value in bad:
            with self.subTest(args=value),self.assertRaises(RepairError):
                validate_repair({'facts':{'observations':facts}},draft(cause,tool,value))

    def test_down_link_cannot_be_repaired_by_changing_mtu(self):
        with self.assertRaises(RepairError):
            validate_repair({'facts':{'observations':[physical(up=False)]}},
                            draft('link_down','ip',['link','set','dev','eth1','mtu','1500']))

    def test_auth_requires_baseline_mode_and_all_observed_key_ids(self):
        cause,facts,tool,args=next(c for c in cases() if c[0]=='ospf_auth_mismatch')
        bad=[args[:2]+['ip ospf message-digest-key 7 md5 PLACEHOLDER'],args[:2]+['no ip ospf authentication'],
             args+['ip ospf authentication message-digest']]
        for value in bad:
            with self.subTest(args=value),self.assertRaises(RepairError):
                validate_repair({'facts':{'observations':facts}},draft(cause,tool,value))

    def test_wrong_bgp_context_and_wrong_hello_value_are_rejected(self):
        for cause in ('ospf_hello_mismatch','bgp_wrong_remote_as','bgp_neighbor_shutdown','bgp_missing_network'):
            _,facts,tool,args=next(c for c in cases() if c[0]==cause)
            value=[x.replace('65001','65002') for x in args]
            if cause=='ospf_hello_mismatch':value[-1]='ip ospf hello-interval 40'
            with self.subTest(cause=cause),self.assertRaises(RepairError):
                validate_repair({'facts':{'observations':facts}},draft(cause,tool,value))

    def test_auth_capture_preserves_ids_but_never_key_material(self):
        parsed=parse('interface eth1\n ip ospf authentication message-digest\n ip ospf message-digest-key 7 md5 SECRET_SENTINEL\n')
        self.assertEqual(parsed['interface/eth1/ospf_key_ids'],[7]);self.assertNotIn('SECRET_SENTINEL',str(parsed))
        delta=differences('r1',{},parsed)
        self.assertIn('interface/eth1/ospf_key_ids',[f['key'] for f in delta])

    def test_inbound_cleanup_preserves_existing_prefix_list_entries(self):
        fact=setting('prefix_list/TEMP/seq/5',None,'deny 10.100.5.1/32')
        fact['configuration_context']['baseline_policy_entries']=['prefix_list/TEMP/seq/10']
        with self.assertRaises(RepairError):
            validate_repair({'facts':{'observations':[fact]}},draft('bgp_inbound_filter','vtysh',
                ['configure terminal','no ip prefix-list TEMP']))
        validate_repair({'facts':{'observations':[fact]}},draft('bgp_inbound_filter','vtysh',
            ['configure terminal','no ip prefix-list TEMP seq 5']))

    def test_expected_policy_context_does_not_expose_unrelated_configuration(self):
        baseline=parse('ip prefix-list TEMP seq 10 permit 10.100.1.1/32\n')
        observed=parse('ip prefix-list TEMP seq 10 permit 10.100.1.1/32\nip prefix-list TEMP seq 5 permit 10.100.5.1/32\n'
                       'route-map IMPORT deny 5\n match ip address prefix-list TEMP\n')
        fact=next(f for f in differences('r1',baseline,observed) if f['key']=='prefix_list/TEMP/seq/5')
        self.assertEqual(fact['configuration_context']['baseline_policy_entries'],['prefix_list/TEMP/seq/10'])

    def test_engine_rejects_pilot_style_semantic_error_after_lint(self):
        class Model:
            def generate(self,payload):
                value=['link_down','r1',.8,'Synthetic down interface.',['e1'],
                    [['r1','ip',['link','set','dev','eth1','mtu','1500']]]]
                return dict(done=True,done_reason='stop',prompt_eval_count=10,eval_count=20,response=json.dumps(value))
        eng=DiagnosisEngine(capture=FixtureCapture(fault='down'),model=Model())
        with tempfile.TemporaryDirectory() as tmp,self.assertRaisesRegex(DiagnosisError,'restore_observed_baseline'):
            run_engine(eng,tmp)

    def test_all_ten_classes_complete_pipeline_with_synthetic_model_and_capture(self):
        for cause,facts,tool,args in cases():
            class Capture(FixtureCapture):
                def capture(self,directory):
                    data=super().capture(directory)
                    # Freeze minimal synthetic causal observations; no production lab read occurs.
                    data['facts']['observations']=deepcopy(facts)
                    data['metadata']['facts_sha256']=write(directory/'facts.json',data['facts'])
                    return data
            class Model:
                def generate(self,payload):
                    value=dict(root_cause_class=cause,root_cause_router='r1',confidence=.8,
                        explanation='Synthetic baseline deviation.',evidence_ids=['e1'],
                        commands=[dict(router='r1',interpreter=tool,args=args)])
                    if payload['format'].get('type')=='array':
                        value=[cause,'r1',.8,value['explanation'],['e1'],[['r1',tool,args]]]
                    return dict(done=True,done_reason='stop',prompt_eval_count=10,eval_count=20,response=json.dumps(value))
            with self.subTest(cause=cause),tempfile.TemporaryDirectory() as tmp:
                job=run_engine(DiagnosisEngine(capture=Capture(),model=Model()),tmp)
                self.assertEqual(job['state'],'completed');self.assertFalse(job['execution_allowed'])
                self.assertEqual(job['result']['root_cause_class'],cause)
                self.assertEqual(job['assessment']['commands'][0]['args'],args)
