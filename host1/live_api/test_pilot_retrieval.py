"""Synthetic regressions for pilot retrieval failures; no Chroma or network calls."""
from copy import deepcopy
import unittest
from .retrieval import query_from_facts, command_reference, retrieve


def physical():
    return dict(type='physical',expected_mtu=1500,endpoints=[
        dict(expected_ipv4='10.0.12.1/30',observed=dict(admin_up=True,mtu=1500,ipv4=['10.0.212.1/30']))])


class PilotRetrievalTests(unittest.TestCase):
    def test_wrong_ip_does_not_inject_mtu_terms(self):
        q=query_from_facts([dict(type='setting',key='interface/eth1/addresses'),physical()])
        self.assertIn('ip address subnet',q);self.assertNotIn('MTU',q);self.assertNotIn('mtu-ignore',q)
        doc=command_reference(q)
        self.assertIn('ip address ADDRESS/PREFIX',doc['content'])
        self.assertEqual(doc['selection_origin'],'verified_live_expansion')

    def test_physical_query_compares_each_observed_dimension(self):
        f=physical();f['endpoints'][0]['observed']['ipv4']=['10.0.12.1/30']
        self.assertNotIn('MTU',query_from_facts([f]))
        f['endpoints'][0]['observed'].update(admin_up=False,mtu=1400)
        q=query_from_facts([f]);self.assertIn('admin down',q);self.assertIn('MTU',q)

    def test_missing_network_prefers_basic_advertisement_not_conditional_advertisement(self):
        q=query_from_facts([dict(type='setting',key='bgp/networks')])
        calls=[];verified=[]
        hit=dict(id='synthetic',text='BGP conditional advertisement with advertise-map',
                 metadata=dict(citation_url='https://example.invalid/synthetic',sha256='0'*64,content_kind='cli_documentation'))
        def search(*args,**kwargs):calls.append((args,kwargs));return {'hits':[hit]}
        docs=retrieve(q,search=search,verify=lambda h,p:verified.append(h['id']))
        self.assertEqual(len(calls),1);self.assertEqual(verified,['synthetic'])
        self.assertIn('network A.B.C.D/M',docs[0]['content']);self.assertIn('adds the announcement',docs[0]['content'])
        self.assertEqual(docs[1]['selection_origin'],'chroma_hybrid')

    def test_specific_address_reference_wins_over_incidental_mtu_term(self):
        doc=command_reference('FRR interface ip address subnet OSPF MTU interface mismatch')
        self.assertIn('ip address',doc['content'])

    def test_supported_setting_topics_have_hash_verified_command_references(self):
        for key,expected in [('neighbor/10.0.12.2/remote_as','remote-as ASN'),
            ('interface/eth1/ospf_hello','ip ospf hello-interval'),
            ('interface/eth1/ospf_area','ip ospf area AREA'),
            ('interface/eth1/ospf_authentication','ip ospf authentication message-digest'),
            ('route_map/IMPORT/deny/5','neighbor PEER route-map')]:
            with self.subTest(key=key):
                doc=command_reference(query_from_facts([dict(type='setting',key=key)]))
                self.assertIn(expected,doc['content']);self.assertEqual(len(doc['original_source_sha256']),64)
