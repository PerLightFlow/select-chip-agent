"""Native streaming contract and cleanup, using only mock HTTP responses."""
import io
import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from stream_check import check_stream


class StreamCheckTests(unittest.TestCase):
    def client(self, frames):
        client = MagicMock()
        client.base = 'http://127.0.0.1:18083'
        client.token = 'synthetic-token'
        client.call.side_effect = [{'data': {'id': 'synthetic-session'}}, {'success': True}]
        wire = ': heartbeat\n\nevent: message\n' + ''.join(
            'data: ' + json.dumps(frame) + '\n\n' for frame in frames)
        client.opener.open.return_value = io.BytesIO(wire.encode())
        return client

    def assert_deleted(self, client):
        self.assertEqual(client.call.call_count, 2)
        client.call.assert_called_with('DELETE', '/sessions/synthetic-session')

    def test_answer_and_complete_succeed_without_returning_content(self):
        client = self.client([
            {'response_type': 'answer', 'content': 'OK', 'done': False},
            {'response_type': 'answer', 'content': '', 'done': True},
            {'response_type': 'complete', 'data': {'final_content': 'OK'}}])
        result = check_stream(client, 'synthetic-model')
        self.assertTrue(result['passed'])
        self.assertEqual(result['answer_characters'], 2)
        self.assertNotIn('OK', json.dumps(result))
        self.assert_deleted(client)
        request = client.opener.open.call_args.args[0]
        self.assertEqual(request.full_url,
                         'http://127.0.0.1:18083/api/v1/knowledge-chat/synthetic-session')
        self.assertEqual(client.opener.open.call_args.kwargs, {'timeout': 90})
        payload = json.loads(request.data)
        self.assertEqual(payload['agent_id'], 'builtin-quick-answer')
        self.assertFalse(payload['agent_enabled'])
        self.assertFalse(payload['web_search_enabled'])
        self.assertEqual(payload['knowledge_base_ids'], [])
        self.assertTrue(payload['disable_title'])
        self.assertEqual(payload['summary_model_id'], 'synthetic-model')
        self.assertNotIn('reasoning_effort', payload)

    def test_error_then_complete_fails_even_with_partial_answer(self):
        secret = 'synthetic-private-provider-details'
        client = self.client([
            {'response_type': 'answer', 'content': 'partial answer'},
            {'response_type': 'error', 'content': secret},
            {'response_type': 'complete', 'data': {'final_content': secret}}])
        with self.assertRaisesRegex(RuntimeError, 'reported an error') as caught:
            check_stream(client, 'model')
        self.assertNotIn(secret, str(caught.exception))
        self.assert_deleted(client)

    def test_empty_complete_fails(self):
        client = self.client([{'response_type': 'complete', 'data': {'final_content': ''}}])
        with self.assertRaisesRegex(RuntimeError, 'nonempty answer'):
            check_stream(client, 'model')
        self.assert_deleted(client)

    def test_error_text_in_complete_is_not_treated_as_an_answer(self):
        client = self.client([{'response_type': 'complete', 'data': {
            'final_content': 'temperature: only 1 is allowed for this model'}}])
        with self.assertRaisesRegex(RuntimeError, 'nonempty answer'):
            check_stream(client, 'model')
        self.assert_deleted(client)

    def test_reasoning_content_does_not_substitute_for_answer(self):
        client = self.client([
            {'response_type': 'thought', 'content': 'thinking'},
            {'response_type': 'answer', 'content': '  '},
            {'response_type': 'complete', 'data': {}}])
        with self.assertRaisesRegex(RuntimeError, 'nonempty answer'):
            check_stream(client, 'model')
        self.assert_deleted(client)

    def test_answer_without_complete_fails(self):
        client = self.client([{'response_type': 'answer', 'content': 'OK', 'done': True}])
        with self.assertRaisesRegex(RuntimeError, 'completion'):
            check_stream(client, 'model')
        self.assert_deleted(client)

    def test_http_failure_is_redacted_and_session_deleted(self):
        client = self.client([])
        client.opener.open.side_effect = HTTPError(
            client.base, 400, 'private-provider-details', {}, io.BytesIO(b'private-body'))
        with self.assertRaisesRegex(RuntimeError, 'transport or format') as caught:
            check_stream(client, 'model')
        self.assertNotIn('private', str(caught.exception))
        self.assert_deleted(client)

    def test_malformed_event_is_redacted_and_session_deleted(self):
        client = self.client([])
        client.opener.open.return_value = io.BytesIO(b'data: not-json-private-details\n')
        with self.assertRaisesRegex(RuntimeError, 'transport or format') as caught:
            check_stream(client, 'model')
        self.assertNotIn('private-details', str(caught.exception))
        self.assert_deleted(client)

    def test_explicit_reasoning_override_is_sent(self):
        client = self.client([{'response_type': 'answer', 'content': 'OK'},
                              {'response_type': 'complete', 'data': {}}])
        result = check_stream(client, 'model', reasoning_effort='off')
        self.assertEqual(json.loads(client.opener.open.call_args.args[0].data)['reasoning_effort'], 'off')
        self.assertEqual(result['reasoning_effort'], 'off')
        self.assert_deleted(client)

    def test_cleanup_failure_cannot_report_success(self):
        client = self.client([{'response_type': 'answer', 'content': 'OK'},
                              {'response_type': 'complete', 'data': {}}])
        client.call.side_effect = [{'data': {'id': 'synthetic-session'}},
                                   RuntimeError('private-cleanup-details')]
        with self.assertRaisesRegex(RuntimeError, 'cleanup failed') as caught:
            check_stream(client, 'model')
        self.assertNotIn('private-cleanup-details', str(caught.exception))
        self.assert_deleted(client)

    def test_complete_stops_reading_without_waiting_for_eof(self):
        client = self.client([])

        class PersistentStream:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def __iter__(self):
                yield b'data: {"response_type":"answer","content":"OK"}\n'
                yield b'data: {"response_type":"complete","data":{}}\n'
                raise AssertionError('Read attempted after terminal frame')

        client.opener.open.return_value = PersistentStream()
        self.assertTrue(check_stream(client, 'model')['passed'])
        self.assert_deleted(client)

    def test_heartbeats_cannot_extend_total_time_limit(self):
        client = self.client([])
        client.opener.open.return_value = io.BytesIO(
            b'data: {"response_type":"agent_query","data":{"assistant_message_id":"assistant-test"}}\n'
            b': heartbeat\n: heartbeat\n')
        client.call.side_effect = [{'data': {'id': 'synthetic-session'}},
                                   {'success': True}, {'success': True}]
        with patch('stream_check.time.monotonic', side_effect=[0, 1, 119, 121]):
            with self.assertRaisesRegex(RuntimeError, 'total time limit'):
                check_stream(client, 'model')
        self.assertEqual(client.call.call_count, 3)
        self.assertEqual(client.call.call_args_list[-2].args,
                         ('POST', '/sessions/synthetic-session/stop', {'message_id': 'assistant-test'}))
        client.call.assert_called_with('DELETE', '/sessions/synthetic-session')

    def test_stop_and_delete_failures_do_not_hide_primary_failure(self):
        client = self.client([
            {'response_type': 'agent_query', 'assistant_message_id': 'assistant-test'},
            {'response_type': 'error', 'content': 'private-primary-details'}])
        client.call.side_effect = [{'data': {'id': 'synthetic-session'}},
                                   RuntimeError('private-stop-failure'),
                                   RuntimeError('private-delete-failure')]
        with self.assertRaisesRegex(RuntimeError, 'reported an error') as caught:
            check_stream(client, 'model')
        self.assertNotIn('private', str(caught.exception))
        self.assertEqual(client.call.call_count, 3)
        self.assertEqual(client.call.call_args_list[-2].args,
                         ('POST', '/sessions/synthetic-session/stop', {'message_id': 'assistant-test'}))
        client.call.assert_called_with('DELETE', '/sessions/synthetic-session')


if __name__ == '__main__':
    unittest.main()
