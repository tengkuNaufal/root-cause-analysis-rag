import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from telemetry.collector import collect_snapshot, normalize, observe


class TelemetryTests(unittest.TestCase):
    def test_interface_down_and_missing_counters_are_not_healthy_defaults(self):
        data = normalize('interfaces', [{'ifname': 'eth1', 'flags': ['BROADCAST'], 'mtu': 1400, 'operstate': 'DOWN'}])[0]
        self.assertFalse(data['admin_up'])
        self.assertFalse(data['lower_up'])
        self.assertEqual(data['mtu'], 1400)
        self.assertIsNone(data['counters'])

    def test_empty_neighbors_differ_from_wrong_schema(self):
        self.assertEqual(normalize('ospf', {'neighbors': {}}), [])
        with self.assertRaises(KeyError):
            normalize('ospf', {'error': 'daemon unavailable'})

    def test_idle_bgp_is_valid_observation_not_collection_error(self):
        data = normalize('bgp', {'peers': {'10.0.35.2': {'remoteAs': 65002, 'state': 'Idle'}}})
        self.assertEqual(data['peers'][0]['state'], 'Idle')
        self.assertIsNone(data['peers'][0]['prefixes_received'])

    def test_route_candidates_and_recursive_nexthops_preserved(self):
        hops = [{'ip': '10.255.0.3', 'recursive': True}, {'interfaceName': 'eth2', 'fib': True}]
        data = normalize('routes', {'10.100.5.1/32': [{'protocol': 'bgp', 'installed': True, 'nexthops': hops}, {'protocol': 'ospf'}]})
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['nexthops'], hops)
        self.assertFalse(data[1]['installed'])

    def test_transport_failures_preserve_raw_and_null_data(self):
        cases = [
            (lambda *a, **kw: subprocess.CompletedProcess(a, 1, '', 'No such container'), 'command_failed'),
            (lambda *a, **kw: subprocess.CompletedProcess(a, 0, 'not json', ''), 'invalid_payload'),
            (lambda *a, **kw: subprocess.CompletedProcess(a, 0, '{"unexpected":true}', ''), 'invalid_payload'),
        ]
        def timeout(*a, **kw):
            raise subprocess.TimeoutExpired(a, 1, output=b'partial')
        cases.append((timeout, 'timeout'))
        with tempfile.TemporaryDirectory() as directory:
            for runner, kind in cases:
                with self.subTest(kind=kind):
                    target = Path(directory) / 'raw.json'
                    observation = observe('clab-rca-r1', 'bgp', target, 1, runner)
                    self.assertEqual(observation['error']['kind'], kind)
                    self.assertIsNone(observation['data'])
                    self.assertEqual(json.loads(target.read_text())['status'], 'error')
                    self.assertIn('+00:00', observation['completed_at'])

    def test_one_source_failure_does_not_discard_other_router_data(self):
        payloads = {'interfaces': '[]', 'ospf': '{"neighbors":{}}', 'bgp': '{"peers":{}}', 'routes': '{}', 'kernel_routes': '[]'}
        def fake_observe(container, source, path, timeout):
            failed = container.endswith('r1') and source == 'bgp'
            runner = lambda *a, **kw: subprocess.CompletedProcess(a, 1 if failed else 0, '' if failed else payloads[source], 'failure' if failed else '')
            return observe(container, source, path, timeout, runner)
        plan = {'lab_name': 'rca', 'nodes': [{'name': 'r1', 'asn': 65001}, {'name': 'r5', 'asn': 65002}],
                'links': [{'protocol': 'ospf', 'endpoints': [{'router': 'r1'}]}]}
        with tempfile.TemporaryDirectory() as directory, patch('telemetry.collector.observe', side_effect=fake_observe):
            result = collect_snapshot(plan, Path(directory) / 'snapshot')
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['source_counts'], {'ok': 8, 'error': 1, 'not_applicable': 1})
        self.assertEqual(result['routers']['r5']['sources']['bgp']['data']['peers'], [])


if __name__ == '__main__':
    unittest.main()
