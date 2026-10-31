import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from deploy import replace_env

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

if __name__ == '__main__': unittest.main()
