import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from services.proxy_pool_service import ProxyPoolService, account_route_key
from services.proxy_subscription_service import ProxySubscriptionService
from services.proxy_core_service import ProxyCoreService
from services import openai_backend_api as backend


class ProxyPoolTests(unittest.TestCase):
    def setUp(self):
        self.pool = ProxyPoolService()
        self.pool.update_settings({'enabled': True})
        self.entries = self.pool.add_entries(['http://exit-a:8080', 'http://exit-b:8080'])['added']

    def test_binding_borrowing_and_recovery_hysteresis(self):
        primary = self.entries[0]['id']
        for _ in range(2):
            self.pool.record_failure(primary, 'connection refused')
        self.assertEqual(self.pool.route_bound(primary, 'account')[0]['id'], primary)
        self.pool.record_failure(primary, 'connection refused')
        borrowed, route = self.pool.route_bound(primary, 'account')
        self.assertEqual(route, 'borrowed')
        self.assertEqual(borrowed['id'], self.entries[1]['id'])
        self.assertEqual(self.pool.route_bound(primary, 'account')[0]['id'], borrowed['id'])
        self.pool.record_success(primary, probe=True)
        self.assertEqual(self.pool.route_bound(primary, 'account')[0]['id'], borrowed['id'])
        self.pool.record_success(primary, probe=True)
        self.assertEqual(self.pool.route_bound(primary, 'account')[0]['id'], primary)

    def test_anonymous_rotation_and_stable_unbound_routing(self):
        self.assertNotEqual(self.pool.route_anonymous()[0]['id'], self.pool.route_anonymous()[0]['id'])
        self.assertEqual(self.pool.route_unbound('account'), self.pool.route_unbound('account'))
        self.assertEqual(account_route_key({'email': 'A@example.com', 'access_token': 'old'}),
                         account_route_key({'email': 'a@example.com', 'access_token': 'new'}))

    def test_http_rejection_does_not_penalize_exit(self):
        entry = self.entries[0]
        session = SimpleNamespace(request=Mock(return_value=SimpleNamespace(status_code=404)))
        self.pool.track_session(session, SimpleNamespace(proxy_id=entry['id']))
        session.request('POST', 'https://chatgpt.com/backend-api/f/conversation')
        self.assertNotEqual(self.pool.health(entry['id'])['state'], 'unhealthy')

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'pool.json'
            pool = ProxyPoolService(path)
            entry = pool.add_entries(['http://exit:8080'])['added'][0]
            pool.update_settings({'enabled': True})
            restored = ProxyPoolService(path)
            self.assertTrue(restored.is_enabled())
            self.assertEqual(restored.get_entry(entry['id'])['url'], entry['url'])

    def test_backend_fails_closed_when_enabled_pool_empty(self):
        for entry in self.entries:
            self.pool.update_entry(entry['id'], {'enabled': False})
        client = object.__new__(backend.OpenAIBackendAPI)
        client.access_token = ''
        with patch.object(backend, 'proxy_pool', self.pool):
            with self.assertRaisesRegex(RuntimeError, 'no available egress'):
                client._egress_profile()

    def test_subscription_refresh_preserves_binding_and_recovers_missing_node(self):
        text = 'proxies:\n- {name: exit, type: http, server: first, port: 8080}\n'
        fetcher = Mock(return_value=(text, ''))
        subscriptions = ProxySubscriptionService(None, pool=self.pool, core=ProxyCoreService(None), fetcher=fetcher)
        sub = subscriptions.create(name='test', url='https://example.com/sub')
        subscriptions.refresh(sub['id'])
        entry = subscriptions.import_nodes(sub['id'], ['exit'])['added'][0]
        fetcher.return_value = (text.replace('first', 'second'), '')
        subscriptions.refresh(sub['id'])
        self.assertEqual(self.pool.get_entry(entry['id'])['url'], 'http://second:8080')
        fetcher.side_effect = RuntimeError('offline')
        self.assertFalse(subscriptions.refresh(sub['id'])['ok'])
        self.assertTrue(self.pool.get_entry(entry['id'])['enabled'])
        fetcher.side_effect = None
        fetcher.return_value = ('proxies:\n- {name: other, type: http, server: other, port: 8080}\n', '')
        subscriptions.refresh(sub['id'])
        self.assertFalse(self.pool.get_entry(entry['id'])['enabled'])
        fetcher.return_value = (text, '')
        subscriptions.refresh(sub['id'])
        self.assertTrue(self.pool.get_entry(entry['id'])['enabled'])


if __name__ == '__main__':
    unittest.main()
