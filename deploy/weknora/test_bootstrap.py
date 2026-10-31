"""Exercise the real bootstrap CLI against the registration contract."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest


class BootstrapTest(unittest.TestCase):
    def check_registration(self, existing=False):
        state = {'registered': False, 'registrations': 0, 'keys': [], 'grants': {}}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self, status, payload):
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode())

            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.path.endswith('/auth/login'):
                    if not state['registered']:
                        return self.respond(401, {'success': False})
                    return self.respond(200, {'success': True, 'token': 'synthetic-token', 'active_tenant': {'id': 1}})
                if self.path.endswith('/auth/register'):
                    password = data['password']
                    if not (8 <= len(password) <= 32 and any(c.isalpha() for c in password) and any(c.isdigit() for c in password)):
                        return self.respond(400, {'success': False})
                    state.update(registered=True, registrations=state['registrations'] + 1)
                    return self.respond(200, {'success': True})
                if self.path.endswith('/api-keys'):
                    state['grants'][data['name']] = data
                    state['keys'].append({'id': data['name'], 'name': data['name'], 'api_key': 'synthetic-key'})
                    return self.respond(200, {'success': True, 'data': {
                        'id': data['name'], 'api_key': 'encrypted-storage-value', 'token': 'synthetic-key'}})
                self.respond(404, {'success': False})

            def do_PUT(self):
                data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                state['grants'][data['name']] = data
                self.respond(200, {'success': True, 'data': {'api_key': 'encrypted-storage-value'}})

            def do_PATCH(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.respond(200, {'success': True, 'data': {'id': 'kb-1'}})

            def do_GET(self):
                if self.path.endswith('/knowledge-bases/kb-1'):
                    if self.headers.get('X-API-Key') != 'synthetic-key' or self.headers.get('Authorization'):
                        return self.respond(401, {'success': False})
                    data = {'id': 'kb-1'}
                elif self.path.endswith('/models'):
                    data = [{'id': 'model-1', 'name': 'qwen3-embedding:0.6b', 'type': 'Embedding'}]
                elif self.path.endswith('/knowledge-bases'):
                    data = [{'id': 'kb-1', 'name': 'select-chip-agent/common'}]
                else:
                    data = state['keys']
                self.respond(200, {'success': True, 'data': data})

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'bootstrap.json'
                url = f'http://127.0.0.1:{server.server_port}'
                if existing:
                    path.write_text(json.dumps({'email': 'test@integration.invalid', 'username': 'synthetic-user',
                        'password': 'A1' + 'x' * 41, 'url': url, 'collections': {}}))
                command = [sys.executable, str(Path(__file__).with_name('bootstrap.py')), '--url', url, '--state', str(path)]
                for _ in range(2):
                    result = subprocess.run(command, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(state['registrations'], 1)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(json.loads(path.read_text())['collections']['common'], 'kb-1')
                self.assertEqual(json.loads(path.read_text())['read_key'], 'synthetic-key')
                self.assertEqual(json.loads(path.read_text())['write_key'], 'synthetic-key')
                self.assertEqual(state['grants']['select-chip-agent-read']['knowledge_base_ids'], [])
                self.assertEqual(state['grants']['select-chip-agent-read']['capabilities'], ['retrieve'])
                self.assertFalse(state['grants']['select-chip-agent-read']['full_access'])
                self.assertEqual(state['grants']['select-chip-agent-write']['knowledge_base_ids'], ['kb-1'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_new_credentials_satisfy_registration(self):
        self.check_registration()

    def test_unregistered_old_oversized_password_is_repaired(self):
        self.check_registration(existing=True)


if __name__ == '__main__':
    unittest.main()
