"""Deployment boundaries and recovery, without Docker/network or real credentials."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError

import bootstrap
import acceptance
import common
import cutover
import export_operator
import prepare


class PreparationTests(unittest.TestCase):
    def test_health_check_retries_connection_closed_during_app_restart(self):
        from http.client import RemoteDisconnected
        opener = MagicMock()
        healthy = MagicMock()
        healthy.__enter__.return_value.status = 200
        opener.open.side_effect = [RemoteDisconnected('closed during restart'), healthy]
        with patch.object(common.request, 'build_opener', return_value=opener), \
                patch.object(common.time, 'sleep'):
            common.wait_health(seconds=5)
        self.assertEqual(opener.open.call_count, 2)

    def test_wiki_raw_handler_responses_preserve_counts_and_sources(self):
        stats = {'total_pages': 2, 'pending_tasks': 0, 'is_active': False}
        page = {'slug': 'summary/doc-id', 'source_refs': ['doc-id|sample']}
        self.assertEqual(acceptance.wiki_payload(stats), stats)
        self.assertEqual(acceptance.wiki_payload(page), page)
        self.assertEqual(acceptance.wiki_payload({'data': stats}), stats)

    def test_repeated_prepare_retains_encryption_keys_and_login(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'native'
            prepare.prepare(root)
            first = (root / '.env').read_bytes(), (root / 'admin.json').read_bytes()
            prepare.prepare(root)
            self.assertEqual(first, ((root / '.env').read_bytes(), (root / 'admin.json').read_bytes()))
            self.assertEqual((root / '.env').stat().st_mode & 0o777, 0o600)
            self.assertEqual((root / 'admin.json').stat().st_mode & 0o777, 0o600)
            self.assertNotIn('LLM_API_KEY', (root / '.env').read_text())

    def test_lost_env_must_not_rotate_keys_over_existing_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data/postgres').mkdir(parents=True)
            (root / 'data/postgres/PG_VERSION').write_text('17')
            with self.assertRaisesRegex(ValueError, 'restore keys'):
                prepare.prepare(root)
            self.assertFalse((root / '.env').exists())

    def test_symlink_data_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'native'
            outside = Path(directory) / 'outside'
            outside.mkdir()
            (root / 'data').mkdir(parents=True)
            (root / 'data/files').symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'symbolic links'):
                prepare.prepare(root)
            self.assertEqual(list(outside.iterdir()), [])

    def test_environment_is_parsed_as_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'env'
            marker = Path(directory) / 'executed'
            path.write_text(f"export KEY='$(touch {marker})'\nVALUE=hello # comment\n")
            env = common.read_env(path)
            self.assertIn('$(touch', env['KEY'])
            self.assertEqual(env['VALUE'], 'hello')
            self.assertFalse(marker.exists())

    def test_private_write_refuses_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'real'
            target.write_text('keep')
            link = Path(directory) / 'alias'
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                common.private_write(link, 'overwrite')
            self.assertEqual(target.read_text(), 'keep')

    def test_provider_secret_is_not_sent_to_an_unexpected_endpoint(self):
        with self.assertRaisesRegex(ValueError, 'Unexpected model endpoint'):
            bootstrap.model_payload({'LLM_API_KEY': 'test-secret', 'LLM_MODEL': 'test',
                                     'LLM_BASE_URL': 'https://unrelated.invalid/v1'})

    def test_kimi_profile_does_not_force_non_thinking_temperature_on_thinking_calls(self):
        payload = bootstrap.model_payload({'LLM_API_KEY': 'test-only',
            'LLM_MODEL': 'kimi-k3-1-pro-261024', 'LLM_TEMPERATURE': '0.6',
            'LLM_BASE_URL': 'https://ark.cn-beijing.volces.com/api/v3'})
        compat = payload['parameters']['spec']['compat']
        self.assertIs(compat['supports_temperature'], False)
        self.assertNotIn('fixed_temperature', compat)
        self.assertNotIn('temperature', compat.get('extra_body', {}))

    def test_http_error_never_includes_provider_response(self):
        client = common.Client()
        client.opener = MagicMock()
        client.opener.open.side_effect = HTTPError('http://127.0.0.1', 500, 'error', {},
                                                   io.BytesIO(b'private-test-secret'))
        with self.assertRaises(common.ApiError) as raised:
            client.call('POST', '/models', {'api_key': 'private-test-secret'})
        self.assertNotIn('private-test-secret', str(raised.exception))

    def test_native_pipeline_has_both_question_and_wiki_models(self):
        payload = bootstrap.kb_payload('demo', 'embed', 'chat')
        self.assertTrue(payload['indexing_strategy']['wiki_enabled'])
        self.assertTrue(payload['question_generation_config']['enabled'])
        self.assertEqual(payload['summary_model_id'], 'chat')
        self.assertEqual(payload['wiki_config']['synthesis_model_id'], 'chat')


class OperatorOutputTests(unittest.TestCase):
    def state(self, root, passed=True):
        common.save_json(root / 'acceptance.json', {'passed': passed, 'capacity_accepted': False})
        common.save_json(root / 'active.json', {'url': 'http://192.168.85.199:8080'})
        common.save_json(root / 'admin.json', {
            'email': 'test@example.invalid', 'password': 'test-only', 'internal_token': 'not-for-export',
            'invitation': {'invite_url': 'https://example.invalid/invite/test',
                           'expires_at': 'tomorrow', 'token': 'not-for-export'}})

    def test_operator_can_read_minimal_outputs_without_exposing_root_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.state(root)
            original = (root / 'admin.json').read_bytes()
            destination = root / 'operator'
            for _ in range(2):
                export_operator.export_operator(root, destination, os.getuid(), os.getgid())
            self.assertEqual((root / 'admin.json').read_bytes(), original)
            self.assertEqual((root / 'admin.json').stat().st_mode & 0o777, 0o600)
            self.assertEqual(destination.stat().st_mode & 0o777, 0o700)
            for path in destination.iterdir():
                self.assertEqual(path.stat().st_uid, os.getuid())
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertNotIn('not-for-export', path.read_text())
            self.assertEqual(json.loads((destination / 'login.json').read_text())['password'], 'test-only')
            self.assertNotIn('test-only', (destination / 'acceptance.json').read_text())
            self.assertNotIn('test-only', (destination / 'active.json').read_text())

    def test_failed_deployment_does_not_export_login(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.state(root, passed=False)
            with self.assertRaisesRegex(ValueError, 'Successful deployment'):
                export_operator.export_operator(root, root / 'operator', os.getuid(), os.getgid())
            self.assertFalse((root / 'operator').exists())

    def test_operator_symlink_does_not_receive_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.state(root)
            outside = root / 'outside'
            outside.mkdir()
            (root / 'operator').symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'symbolic links'):
                export_operator.export_operator(root, root / 'operator', os.getuid(), os.getgid())
            self.assertEqual(list(outside.iterdir()), [])


class CutoverTests(unittest.TestCase):
    def gate(self, root, passed=True):
        common.save_json(root / 'acceptance.json', {'passed': passed, 'timestamp': 1000})
        common.save_json(root / 'admin.json', {'team_registration_configured': True})
        common.save_env(root / '.env', {'UI_BIND': '127.0.0.1', 'UI_PORT': '18082'})

    def test_failed_gate_never_stops_existing_containers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.gate(root, False)
            with patch.object(cutover, 'ROOT', root), patch.object(cutover, 'command') as command:
                with self.assertRaisesRegex(RuntimeError, 'smoke gate'):
                    cutover.switch()
                command.assert_not_called()

    def test_foreign_port_owner_is_left_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.gate(root)
            container = {'Id': 'unrelated', 'NetworkSettings': {'Ports': {'80/tcp': [{'HostPort': '8080'}]}}}
            with patch.object(cutover, 'ROOT', root), patch.object(cutover.time, 'time', return_value=1000), \
                    patch.object(cutover, 'command', side_effect=['oldapp', 'oldknowledge', 'unrelated',
                                                                json.dumps([container])]) as command:
                with self.assertRaisesRegex(RuntimeError, 'unrecognized'):
                    cutover.switch()
                self.assertFalse(any('stop' in call.args for call in command.call_args_list))

    def test_failed_new_frontend_restores_previous_port_and_containers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.gate(root)
            container = {'Id': 'oldapp-full', 'NetworkSettings': {'Ports': {'80/tcp': [{'HostPort': '8080'}]}}}
            with patch.object(cutover, 'ROOT', root), patch.object(cutover.time, 'time', return_value=1000), \
                    patch.object(cutover.time, 'sleep'), patch.object(cutover, 'compose') as compose, \
                    patch.object(cutover, 'check_ui', side_effect=RuntimeError('frontend failed')), \
                    patch.object(cutover, 'command', side_effect=[
                        'oldapp', 'oldknowledge', 'oldapp', json.dumps([container]), None, None]) as command:
                with self.assertRaisesRegex(RuntimeError, 'frontend failed'):
                    cutover.switch()
                command.assert_any_call('docker', 'start', 'oldapp', 'oldknowledge')
                self.assertEqual(common.read_env(root / '.env')['UI_PORT'], '18082')
                self.assertFalse((root / 'active.json').exists())
                self.assertFalse(any('down' in call.args for call in compose.call_args_list))


if __name__ == '__main__':
    unittest.main()
