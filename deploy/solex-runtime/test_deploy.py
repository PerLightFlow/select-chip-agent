import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from deploy import replace_env, wait_frontend
from acceptance import acceptance_identity

class RuntimeReleaseTests(unittest.TestCase):
    def test_preserves_credentials_and_unrelated_environment_exactly(self):
        raw = "# deployment\nDB_PASSWORD=literal-$-not-a-shell-command\nWEKNORA_APP_IMAGE=old:tag\n"
        updated = replace_env(raw, {'WEKNORA_APP_IMAGE':'solex/app:abc', 'SOLEX_MANAGED_RUNTIME':'true'})
        self.assertIn('DB_PASSWORD=literal-$-not-a-shell-command\n', updated)
        self.assertIn('WEKNORA_APP_IMAGE=solex/app:abc\n', updated)
        self.assertEqual(updated.count('WEKNORA_APP_IMAGE='), 1)
        self.assertIn('SOLEX_MANAGED_RUNTIME=true\n', updated)
    def test_rejects_ambiguous_environment(self):
        with self.assertRaises(ValueError):
            replace_env('WEKNORA_APP_IMAGE=a\nWEKNORA_APP_IMAGE=b\n', {'WEKNORA_APP_IMAGE':'c'})
    def test_rejects_untrusted_image_reference(self):
        with self.assertRaises(ValueError):
            replace_env('', {'WEKNORA_APP_IMAGE':'a\nDB_PASSWORD=x'})
    def test_acceptance_identity_satisfies_complex_password_policy(self):
        identity = acceptance_identity()
        self.assertGreaterEqual(len(identity['password']), 8)
        self.assertLessEqual(len(identity['password']), 32)
        self.assertRegex(identity['password'], r'[A-Za-z]')
        self.assertRegex(identity['password'], r'[0-9]')
        self.assertLessEqual(len(identity['username']), 50)
        self.assertTrue(identity['email'].endswith('@example.invalid'))
    def test_frontend_startup_tolerates_transient_connection_reset(self):
        with patch('deploy.frontend_ok', side_effect=[ConnectionResetError(), None]) as probe, patch('deploy.time.sleep'):
            wait_frontend()
        self.assertEqual(probe.call_count, 2)
    def test_frontend_failure_remains_a_release_failure(self):
        with patch('deploy.frontend_ok', side_effect=RuntimeError('Frontend assets missing')), patch('deploy.time.sleep'), patch('deploy.time.monotonic', side_effect=[0, 1, 91]):
            with self.assertRaisesRegex(RuntimeError, 'Frontend health check timed out'):
                wait_frontend()

if __name__ == '__main__': unittest.main()
