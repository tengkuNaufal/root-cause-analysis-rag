"""Negative integration tests against copies of stored evidence, without touching originals."""
import json
import tempfile
import unittest
from pathlib import Path
from knowledge.evidence import ROOT, canonical_references, context, local_path, read

RUN = ROOT / 'data/host1/integration-faults/20261119T100613Z'
GRAPH = RUN / 'graphs/L12/down/graph.json'


class EvidenceTests(unittest.TestCase):
    def mutate(self, change):
        graph = read(GRAPH)
        change(graph)
        with tempfile.TemporaryDirectory(dir=ROOT / 'data/host1') as folder:
            path = Path(folder) / 'graph.json'
            path.write_text(json.dumps(graph))
            with self.assertRaises((ValueError, FileNotFoundError)):
                context(path, RUN / 'inventory.json', 'L12')

    def test_windows_wsl_path_mapping(self):
        for prefix in ('Z:/example/Tubes', '/example/Tubes', 'Z:/example/root-cause-analysis-rag'):
            self.assertEqual(local_path(prefix + '/knowledge/README.md'), ROOT / 'host1/knowledge/README.md')

    def test_outside_project_rejected(self):
        for path in ('../outside.json', 'Z:/unrelated/file.json', '/unrelated/file.json'):
            with self.assertRaises(ValueError):
                local_path(path)

    def test_migration_aliases_refer_to_same_file(self):
        expected = RUN / 'graphs/L12/down/graph.json'
        for prefix in ('results/', 'data/host1/'):
            self.assertEqual(local_path(prefix + 'integration-faults/20261119T100613Z/graphs/L12/down/graph.json'), expected)
        self.assertEqual(local_path('knowledge/models'), ROOT / 'private/knowledge/models')

    def test_canonical_comparison_retains_hashes_and_observations(self):
        old = dict(path='results/example.json', sha256='original', observation=False)
        new = dict(path='data/host1/example.json', sha256='original', observation=False)
        self.assertEqual(canonical_references(old), canonical_references(new))
        new['sha256'] = 'changed'
        self.assertNotEqual(canonical_references(old), canonical_references(new))
        new.update(sha256='original', observation=True)
        self.assertNotEqual(canonical_references(old), canonical_references(new))

    def test_unknown_link(self):
        with self.assertRaises(ValueError):
            context(GRAPH, RUN / 'inventory.json', 'L99')

    def test_wrong_snapshot_hash(self):
        self.mutate(lambda g: g['graph'].update(snapshot_sha256='bad'))

    def test_missing_snapshot(self):
        self.mutate(lambda g: g['graph'].update(snapshot='data/host1/no-such-snapshot.json'))

    def test_wrong_log_hash(self):
        self.mutate(lambda g: g['graph']['log_inputs'][0].update(sha256='bad'))

    def test_future_event_rejected(self):
        self.mutate(lambda g: next(n for n in g['nodes'] if n['kind'] == 'log_event')['event'].update(event_timestamp='2099-01-01T00:00:00Z'))

    def test_modified_message_rejected(self):
        self.mutate(lambda g: next(n for n in g['nodes'] if n['kind'] == 'log_event')['event'].update(message='forged'))

    def test_modified_interface_rejected(self):
        self.mutate(lambda g: next(n for n in g['nodes'] if n['id'] == 'interface:r1:eth1')['observed'].update(mtu=9000))


if __name__ == '__main__':
    unittest.main()
