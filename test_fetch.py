import json
import subprocess
import unittest
from unittest.mock import patch
import fetch


class RemoteQuotaTests(unittest.TestCase):
    def test_remote_claude_never_reads_local_credentials(self):
        account = {'label': 'Claude', 'kind': 'claude', 'dir': '~/.claude-sub', 'on': 'work'}
        result = {'bars': [{'name': '7d', 'used': 79, 'resets': None}], 'error': None}
        with patch.object(fetch.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps(result), '')) as run, patch.object(fetch, 'claude', side_effect=AssertionError('local credentials read')):
            data = fetch.read(account)
        self.assertEqual(data['bars'], result['bars'])
        self.assertEqual(data['machine'], 'work')
        args, kwargs = run.call_args
        self.assertEqual(args[0][:6], ['hc', 'exec', '-i', '--on', 'work', '--'])
        payload = json.loads(kwargs['input'])
        self.assertNotIn('on', payload['account'])
        self.assertEqual(payload['account']['dir'], '~/.claude-sub')

    def test_offline_host_does_not_fall_back_to_local_login(self):
        for kind in ('claude', 'codex'):
            with self.subTest(kind=kind), patch.object(fetch, 'remote', side_effect=RuntimeError('offline')), patch.object(fetch, kind, side_effect=AssertionError('local login read')):
                data = fetch.read({'kind': kind, 'on': 'work'})
                self.assertEqual(data['error'], 'offline')
                self.assertEqual(data['bars'], [])

    def test_cache_identity_distinguishes_machine_and_login(self):
        with patch.object(fetch, 'remote', return_value={'bars': [], 'error': None}):
            ids = [fetch.read({'label': 'Claude', 'kind': 'claude', 'on': machine, 'dir': directory})['id']
                   for machine in ('personal', 'work') for directory in ('~/.claude', '~/.claude-sub')]
        self.assertEqual(len(set(ids)), 4)

    def test_remote_reader_runs_without_installed_mod(self):
        # Exercise the actual stdin transport and exec namespace in a fresh Python process.
        # An unknown provider returns a per-account error without accessing a credential store.
        run_process = subprocess.run
        def local_transport(argv, **kwargs):
            return run_process(argv[6:], **kwargs)
        with patch.object(fetch.subprocess, 'run', side_effect=local_transport):
            data = fetch.remote({'kind': 'unknown', 'on': 'remote'})
        self.assertEqual(data['bars'], [])
        self.assertIn('unknown', data['error'])


if __name__ == '__main__':
    unittest.main()
