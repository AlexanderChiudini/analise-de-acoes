import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hosting

class HostingTests(unittest.TestCase):
    def test_local_and_exact_deployed_host(self):
        with patch.dict(os.environ, {}, clear=True):
            for value in ('127.0.0.1:8765', 'localhost:1234', hosting.DEPLOYED_HOST):
                self.assertTrue(hosting.allowed_host(value))
            for value in ('evil.vercel.app', hosting.DEPLOYED_HOST+'.evil.com', 'evil.com@localhost', 'localhost,evil.com', None, 'localhost/evil', 'localhost:abc'):
                self.assertFalse(hosting.allowed_host(value))

    def test_platform_and_custom_domain(self):
        env = {'VERCEL_URL':'preview-123.vercel.app', 'VERCEL_PROJECT_PRODUCTION_URL':'analysis.vercel.app', 'ALLOWED_HOSTS':'https://acoes.example.com,other.example.com'}
        with patch.dict(os.environ, env, clear=True):
            for value in ('preview-123.vercel.app','analysis.vercel.app','acoes.example.com','other.example.com'):
                self.assertTrue(hosting.allowed_host(value))
            self.assertFalse(hosting.allowed_host('preview-124.vercel.app'))

    def test_session_works_across_instances_and_expires(self):
        with patch.dict(os.environ, {'VERCEL':'1','SESSION_SECRET':'a'*32}, clear=True):
            with patch.object(hosting.time,'time',return_value=100):
                token = hosting.session_token()
                self.assertTrue(hosting.valid_session(token))
                self.assertFalse(hosting.valid_session(token+'invalid'))
            with patch.object(hosting.time,'time',return_value=86501):
                self.assertFalse(hosting.valid_session(token))
            with patch.dict(os.environ, {'SESSION_SECRET':'b'*32}):
                self.assertFalse(hosting.valid_session(token))

    def test_cloud_requires_stable_secret(self):
        with patch.dict(os.environ, {'VERCEL':'1'}, clear=True):
            with self.assertRaises(hosting.ConfigurationError):
                hosting.session_token()

if __name__ == '__main__':
    unittest.main()
