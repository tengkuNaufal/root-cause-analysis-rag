"""Exercise the actual PowerShell client against localhost HTTP fixtures; no model."""
from contextlib import contextmanager
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / 'laptop/replay.ps1'
SHELL = os.environ.get('HOST2_CLIENT_POWERSHELL') or shutil.which('powershell.exe') or shutil.which('pwsh')


@contextmanager
def backend(mode='normal'):
    class State:
        posts = []
        gets = []
        active = 0
        peak = 0
        lock = threading.Lock()
    state = State()
    scenarios = [dict(id=f'case.{i:02}', profile='mtu-observation', synthetic=True) for i in range(1, 17)]

    def evidence(number):
        run = f'{number:032x}'
        return dict(id='T1', kind='telemetry', source_id='sha256:' + 'a' * 64, sha256='a' * 64,
                    locator='/routers/r1', content='Kutipan baris satu\nMTU = 1500; simbol \u2713',
                    url=f'/v1/runs/{run}/evidence/T1')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, value):
            blob = json.dumps(value, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(blob)))
            self.end_headers()
            try:
                self.wfile.write(blob)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def do_GET(self):
            state.gets.append(self.path)
            if self.path == '/health':
                self.send(200, dict(status='ok', mode='replay_only', active=False, execution_allowed=False))
            elif self.path == '/v1/scenarios':
                selected = scenarios[:-1] if mode == 'short_catalog' else list(scenarios)
                if mode == 'duplicate_catalog':
                    selected[-1] = selected[0]
                self.send(200, dict(api_version='1.0', mode='replay_only', execution_allowed=False, scenarios=selected))
            elif self.path.startswith('/v1/runs/'):
                number = int(self.path.split('/')[3], 16)
                value = evidence(number)
                if mode == 'wrong_evidence':
                    value['content'] = 'different source content'
                self.send(200, value)
            else:
                self.send(404, dict(error=dict(code='not_found')))

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert set(body) == {'scenario_id'}
            number = int(body['scenario_id'].split('.')[1])
            with state.lock:
                state.posts.append(body['scenario_id'])
                state.active += 1
                state.peak = max(state.peak, state.active)
            try:
                time.sleep(2 if mode == 'timeout' else 0.01)
                if mode == 'busy' and number == 4:
                    self.send(503, dict(error=dict(code='agent_busy'), execution_allowed=False))
                    return
                if mode == 'invalid_json':
                    self.send_response(201)
                    self.send_header('Content-Length', '1')
                    self.end_headers()
                    self.wfile.write(b'{')
                    return
                abstain = number == 3
                items = [] if abstain else [evidence(number)]
                if mode == 'wrong_url' and items:
                    items[0]['url'] = '/health'
                status = 'abstain' if abstain else 'hypothesis'
                self.send(201, dict(api_version='1.0', scenario_id=body['scenario_id'], profile='mtu-observation',
                    synthetic=True, mode='replay', run_id=f'{number:032x}', status=status,
                    phase=None if abstain else 'fault', execution_allowed=False, diagnosis_allowed=False,
                    proposed_patch=[], result=dict(status=status, execution_allowed=False, proposed_patch=[]),
                    timing=dict(unit='seconds', agent_seconds=0.001, total_seconds=0.005),
                    model=dict(called=not abstain, requests=0 if abstain else 1), evidence=items,
                    citations=[] if abstain else [dict(evidence_ids=['T1'], evidence_urls=[items[0]['url']])]))
            finally:
                with state.lock:
                    state.active -= 1

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@unittest.skipUnless(SHELL, 'PowerShell is required to test the actual client')
class ReplayClientTests(unittest.TestCase):
    def setUp(self):
        directory = ROOT / 'private/client-tests'
        directory.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=directory)
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / 'results.jsonl'

    def invoke(self, url, timeout=10):
        return subprocess.run([SHELL, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
            '-File', str(CLIENT), '-BaseUrl', url, '-OutputFile', str(self.output), '-TimeoutSec', str(timeout)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', timeout=45)

    def rows(self):
        return [json.loads(line) for line in self.output.read_text(encoding='utf-8').splitlines()]

    def test_all_sixteen_are_sequential_complete_and_utf8(self):
        with backend() as (url, state):
            result = self.invoke(url)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(state.posts, [f'case.{i:02}' for i in range(1, 17)])
            self.assertEqual(state.peak, 1)
            self.assertEqual(len([p for p in state.gets if p.startswith('/v1/runs/')]), 15)
        rows = self.rows()
        self.assertEqual(len(rows), 16)
        self.assertFalse(self.output.read_bytes().startswith(b'\xef\xbb\xbf'))
        self.assertTrue(all(r['client_checks_passed'] for r in rows))
        self.assertEqual(rows[2]['outcome'], 'abstain')
        self.assertIsNone(rows[2]['response']['phase'])
        self.assertEqual(rows[0]['response']['evidence'][0]['content'], 'Kutipan baris satu\nMTU = 1500; simbol \u2713')
        self.assertTrue(rows[0]['first_request_in_session'])
        self.assertTrue(all(not r['first_request_in_session'] for r in rows[1:]))
        self.assertEqual(len({r['client_session_id'] for r in rows}), 1)
        for index, row in enumerate(rows, 1):
            self.assertEqual(row['sequence'], index)
            self.assertEqual(row['http_status'], 201)
            self.assertEqual(row['server_agent_seconds'], 0.001)
            self.assertEqual(row['server_total_seconds'], 0.005)
            self.assertGreaterEqual(row['client_total_seconds'], row['client_response_seconds'])
            self.assertGreaterEqual(row['evidence_fetch_seconds'], 0)
            self.assertIsNone(row['error'])
            self.assertLessEqual(datetime.fromisoformat(row['started_at_utc']), datetime.fromisoformat(row['finished_at_utc']))

    def test_busy_is_logged_without_retry_or_later_posts(self):
        with backend('busy') as (url, state):
            result = self.invoke(url)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertEqual(state.posts, ['case.01', 'case.02', 'case.03', 'case.04'])
        rows = self.rows()
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[-1]['outcome'], 'http_error')
        self.assertEqual(rows[-1]['http_status'], 503)
        self.assertEqual(json.loads(rows[-1]['raw_error_body'])['error']['code'], 'agent_busy')
        self.assertFalse(rows[-1]['server_completion_unknown'])

    def test_timeout_is_logged_as_unknown_completion_and_stops(self):
        with backend('timeout') as (url, state):
            result = self.invoke(url, timeout=1)
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertEqual(state.posts, ['case.01'])
        row, = self.rows()
        self.assertEqual(row['outcome'], 'transport_error')
        self.assertTrue(row['server_completion_unknown'])
        self.assertIsNone(row['http_status'])

    def test_wrong_evidence_is_logged_and_stops(self):
        with backend('wrong_evidence') as (url, state):
            result = self.invoke(url)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertEqual(state.posts, ['case.01'])
        row, = self.rows()
        self.assertEqual(row['outcome'], 'evidence_error')
        self.assertIsNotNone(row['response'])
        self.assertEqual(row['error']['stage'], 'evidence')

    def test_wrong_url_is_rejected_before_fetch(self):
        with backend('wrong_url') as (url, state):
            result = self.invoke(url)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertEqual(state.gets, ['/health', '/v1/scenarios'])
        row, = self.rows()
        self.assertEqual(row['outcome'], 'validation_error')

    def test_invalid_json_is_preserved_in_error_record(self):
        with backend('invalid_json') as (url, state):
            result = self.invoke(url)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertEqual(state.posts, ['case.01'])
        row, = self.rows()
        self.assertEqual(row['outcome'], 'invalid_json')
        self.assertEqual(row['raw_error_body'], '{')
        self.assertFalse(row['server_completion_unknown'])

    def test_invalid_catalog_never_starts_inference(self):
        for mode in ('short_catalog', 'duplicate_catalog'):
            with self.subTest(mode=mode), backend(mode) as (url, state):
                result = self.invoke(url)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertEqual(state.posts, [])
                self.assertFalse(self.output.exists())

    def test_existing_output_is_not_overwritten(self):
        self.output.write_text('existing measurement\n', encoding='utf-8')
        with backend() as (url, state):
            result = self.invoke(url)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertEqual(state.gets, [])
            self.assertEqual(state.posts, [])
        self.assertEqual(self.output.read_text(), 'existing measurement\n')


if __name__ == '__main__':
    unittest.main()
