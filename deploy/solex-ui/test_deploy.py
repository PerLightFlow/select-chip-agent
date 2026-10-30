"""Frontend-only release recovery tests; no network, Docker, or real secrets."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import deploy


class EnvironmentTests(unittest.TestCase):
    def test_only_the_ui_image_line_changes(self):
        before = b'# keep formatting\r\nDB_PASSWORD="test-secret"\r\nWEKNORA_UI_IMAGE="example/ui:old" # prior\r\nUI_PORT=8080\r\n'
        after = deploy.replace_image_setting(before, 'solex/solex-ui:123')
        self.assertEqual(after, b'# keep formatting\r\nDB_PASSWORD="test-secret"\r\nWEKNORA_UI_IMAGE=solex/solex-ui:123\r\nUI_PORT=8080\r\n')
        self.assertEqual(deploy.image_setting(before), 'example/ui:old')

    def test_ambiguous_or_unsafe_settings_are_rejected(self):
        for raw in [b'OTHER=1\n', b'WEKNORA_UI_IMAGE=a\nWEKNORA_UI_IMAGE=b\n']:
            with self.assertRaises(RuntimeError):
                deploy.replace_image_setting(raw, 'solex/solex-ui:123')
        with self.assertRaises(RuntimeError):
            deploy.replace_image_setting(b'WEKNORA_UI_IMAGE=a\n', 'bad\nDB_PASSWORD=changed')

    def test_artifact_digest_detects_changes_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'index.html').write_text('before')
            before = deploy.dist_digest(root)
            (root / 'index.html').write_text('after')
            self.assertNotEqual(deploy.dist_digest(root), before)
            (root / 'linked.html').symlink_to(root / 'index.html')
            with self.assertRaisesRegex(RuntimeError, 'symbolic'):
                deploy.dist_digest(root)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / 'active.json').write_text('{}')
        self.original = b'DB_PASSWORD=test-only\nWEKNORA_UI_IMAGE=example/ui:old\nUI_PORT=8080\n'
        (self.root / '.env').write_bytes(self.original)
        self.meta = {'release_id': 'solex-ui-' + 'a' * 16, 'image': 'solex/solex-ui:' + 'a' * 16,
                     'source_revision': 'b' * 40, 'dist_sha256': 'c' * 64}
        self.containers = {'frontend': {'Id': 'frontend-old', 'Image': 'old-id', 'State': {'Running': True}}}
        for service in deploy.EXPECTED_OTHERS:
            self.containers[service] = {'Id': service + '-id', 'Image': service + '-image', 'RestartCount': 0,
                                        'State': {'Running': True, 'StartedAt': 'unchanged', 'Health': {'Status': 'healthy'}}}
        self.patches = [
            patch.object(deploy, 'ROOT', self.root), patch.object(deploy, 'metadata', return_value=self.meta),
            patch.object(deploy, 'native_containers', return_value=self.containers),
            patch.object(deploy, 'check_ui', return_value={'registration_mode': 'invite_register'}),
            patch.object(deploy, 'command', return_value=json.dumps([{'Id': 'old-id'}])),
            patch.object(deploy, 'build_image', return_value='new-id'),
            patch.object(deploy, 'start_canary'), patch.object(deploy, 'assert_frontend_image'), patch('sys.stdout', new_callable=io.StringIO),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temporary.cleanup()

    def test_canary_failure_cannot_change_public_environment_or_frontend(self):
        with patch.object(deploy, 'wait_ui', side_effect=RuntimeError('canary failed')), \
                patch.object(deploy, 'compose_frontend') as compose, patch.object(deploy, 'remove_canary') as remove:
            with self.assertRaisesRegex(RuntimeError, 'canary failed'):
                deploy.release()
        self.assertEqual((self.root / '.env').read_bytes(), self.original)
        compose.assert_not_called()
        remove.assert_called_once_with(self.meta)

    def test_public_gate_failure_restores_exact_environment_and_previous_frontend(self):
        with patch.object(deploy, 'wait_ui', side_effect=[None, RuntimeError('public failed'), None]), \
                patch.object(deploy, 'compose_frontend') as compose, patch.object(deploy, 'remove_canary'):
            with self.assertRaisesRegex(RuntimeError, 'public failed'):
                deploy.release()
        self.assertEqual((self.root / '.env').read_bytes(), self.original)
        self.assertEqual(compose.call_count, 2)
        state = json.loads((self.root / 'ui-releases' / self.meta['release_id'] / 'acceptance.json').read_text())
        self.assertTrue(state['rolled_back'])
        self.assertFalse(state['passed'])
        self.assertEqual(set(state['other_services']), deploy.EXPECTED_OTHERS)
        self.assertFalse((self.root / 'solex-ui-active.json').exists())

    def test_success_changes_only_image_setting_and_keeps_private_recovery_copy(self):
        with patch.object(deploy, 'wait_ui'), patch.object(deploy, 'compose_frontend') as compose, \
                patch.object(deploy, 'remove_canary'):
            deploy.release()
        self.assertEqual((self.root / '.env').read_bytes(), deploy.replace_image_setting(self.original, self.meta['image']))
        compose.assert_called_once_with()
        backup = self.root / 'ui-releases' / self.meta['release_id'] / 'env.before'
        self.assertEqual(backup.read_bytes(), self.original)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        state = json.loads((self.root / 'solex-ui-active.json').read_text())
        self.assertTrue(state['passed'])
        self.assertNotIn('test-only', json.dumps(state))

    def test_backend_restart_during_canary_prevents_public_cutover(self):
        def restart_backend(*_args, **_kwargs):
            self.containers['app']['RestartCount'] = 1
        with patch.object(deploy, 'wait_ui', side_effect=restart_backend), \
                patch.object(deploy, 'compose_frontend') as compose, patch.object(deploy, 'remove_canary'):
            with self.assertRaisesRegex(RuntimeError, 'Another native service changed'):
                deploy.release()
        compose.assert_not_called()
        self.assertEqual((self.root / '.env').read_bytes(), self.original)

    def test_external_environment_change_is_never_overwritten(self):
        def modify_environment(*_args, **_kwargs):
            (self.root / '.env').write_bytes(self.original + b'EXTERNAL_SETTING=keep\n')
        with patch.object(deploy, 'wait_ui', side_effect=modify_environment), \
                patch.object(deploy, 'compose_frontend') as compose, patch.object(deploy, 'remove_canary'):
            with self.assertRaisesRegex(RuntimeError, 'environment changed'):
                deploy.release()
        compose.assert_not_called()
        self.assertTrue((self.root / '.env').read_bytes().endswith(b'EXTERNAL_SETTING=keep\n'))


if __name__ == '__main__':
    unittest.main()
