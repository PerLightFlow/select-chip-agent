import json
from unittest.mock import patch

import httpx
from django.test import SimpleTestCase, override_settings

from core.providers import chat_json, ProviderUnavailable
from core.workflow import parse_requirements


@override_settings(LLM_BASE_URL='https://provider.invalid/v3',
    LLM_API_KEY='test-secret', LLM_MODEL='test-model', LLM_THINKING='', LLM_TEMPERATURE=0)
class ChatProviderTests(SimpleTestCase):
    def response_client(self, handler):
        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_generic_provider_omits_optional_thinking(self):
        def handler(request):
            body = json.loads(request.content)
            self.assertNotIn('thinking', body)
            self.assertEqual(body['temperature'], 0)
            return httpx.Response(200, json={'choices': [{'message': {'content': '{"ok":true}'}}]})
        with patch('core.providers.httpx.Client', return_value=self.response_client(handler)):
            self.assertEqual(chat_json('Return JSON', 'ping'), {'ok': True})

    @override_settings(LLM_THINKING='disabled', LLM_TEMPERATURE=0.6,
        LLM_MODEL='kimi-k3-1-pro-261024')
    def test_ark_kimi_json_reaches_validated_requirements(self):
        def handler(request):
            body = json.loads(request.content)
            self.assertEqual(body['thinking'], {'type': 'disabled'})
            self.assertEqual(body['temperature'], 0.6)
            self.assertEqual(body['model'], 'kimi-k3-1-pro-261024')
            self.assertEqual(body['response_format'], {'type': 'json_object'})
            self.assertEqual(request.headers['Authorization'], 'Bearer test-secret')
            content = {'requirements': [{'key': 'os', 'op': 'eq', 'value': 'Linux',
                'unit': '', 'hard': True, 'source': 'Linux', 'conditions': ''}],
                'questions': [], 'task': ''}
            return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(content)}}]})
        with patch('core.providers.httpx.Client', return_value=self.response_client(handler)):
            result = parse_requirements('需要 Linux 系统')
        self.assertEqual(result['mode'], 'llm')
        self.assertEqual(result['requirements'][0]['value'], 'Linux')

    def test_provider_failure_keeps_form_fallback_without_secret(self):
        def handler(request):
            return httpx.Response(401, json={'error': 'invalid test-secret'})
        with patch('core.providers.httpx.Client', return_value=self.response_client(handler)):
            result = parse_requirements('需要 Linux 系统')
        self.assertEqual(result['mode'], 'form')
        self.assertNotIn('test-secret', json.dumps(result))

    @override_settings(LLM_THINKING='invalid')
    def test_invalid_thinking_fails_before_network(self):
        with patch('core.providers.httpx.Client') as client:
            with self.assertRaises(ProviderUnavailable):
                chat_json('Return JSON', 'ping')
            client.assert_not_called()
