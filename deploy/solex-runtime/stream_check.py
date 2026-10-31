"""Exercise a disposable native chat stream without returning response contents."""
import json
import sys
import time
from urllib import parse, request


class _StreamDeadlineExceeded(Exception):
    pass


def check_stream(client, model_id=None, reasoning_effort=None, agent_id="builtin-quick-answer"):
    """Require an answer, completion and no error; always delete our test session.

    ``client`` is an already authenticated common.Client (or a compatible
    object). Only counters are returned, so callers can safely save the result
    with deployment evidence. A completion's final_content is deliberately not
    counted as an answer: WeKnora can persist an upstream error in that field.
    """
    try:
        session = client.call('POST', '/sessions', {
            'title': '__native_stream_acceptance__',
            'description': 'Synthetic model streaming verification'})['data']
        session_id = session['id']
        if not isinstance(session_id, str) or not session_id:
            raise ValueError('Missing test session ID')
    except Exception:
        raise RuntimeError('Native stream session creation failed; response omitted') from None

    session_path = '/sessions/' + parse.quote(session_id, safe='')
    complete = False
    assistant_message_id = None
    try:
        payload = {
            'query': '请仅回答 OK，不调用工具。',
            'agent_id': agent_id,
            'agent_enabled': False,
            'knowledge_base_ids': [],
            'web_search_enabled': False,
            'disable_title': True,
        }
        if model_id:
            payload["summary_model_id"] = model_id
        if reasoning_effort is not None:
            payload['reasoning_effort'] = reasoning_effort
        req = request.Request(
            client.base.rstrip('/') + '/api/v1/knowledge-chat/' + parse.quote(session_id, safe=''),
            data=json.dumps(payload).encode(), method='POST',
            headers={'Authorization': 'Bearer ' + client.token,
                     'Content-Type': 'application/json', 'Accept': 'text/event-stream'})
        answers = 0
        answer_characters = 0
        error_seen = False
        deadline = time.monotonic() + 120
        try:
            with client.opener.open(req, timeout=90) as response:
                for raw in response:
                    # Heartbeats keep a socket alive indefinitely. The entire
                    # stream also has a time budget, independent of read timeout.
                    if time.monotonic() >= deadline:
                        raise _StreamDeadlineExceeded
                    line = raw.decode('utf-8').strip()
                    if not line.startswith('data:'):
                        continue
                    data = line[5:].strip()
                    if not data or data == '[DONE]':
                        continue
                    frame = json.loads(data)
                    if not isinstance(frame, dict):
                        raise ValueError('Invalid stream frame')
                    kind = frame.get('response_type')
                    message_id = frame.get('assistant_message_id')
                    if kind == 'agent_query' and isinstance(frame.get('data'), dict):
                        message_id = frame['data'].get('assistant_message_id') or message_id
                    if isinstance(message_id, str) and message_id:
                        assistant_message_id = message_id
                    if kind == 'error':
                        error_seen = True
                    elif kind == 'answer':
                        content = frame.get('content')
                        if isinstance(content, str) and content.strip():
                            answers += 1
                            answer_characters += len(content)
                    elif kind == 'complete':
                        complete = True
                        # The server may retain the SSE connection after the
                        # terminal event. Do not wait for EOF to finish our test.
                        break
        except _StreamDeadlineExceeded:
            raise RuntimeError('Native stream exceeded its total time limit; response omitted') from None
        except Exception:
            raise RuntimeError('Native stream transport or format failed; response omitted') from None
        if error_seen:
            raise RuntimeError('Native stream reported an error; response omitted')
        if not answers or not complete:
            raise RuntimeError('Native stream lacks a nonempty answer or completion; response omitted')
        return {'passed': True, 'answer_frames': answers, 'answer_characters': answer_characters,
                'complete': True, 'error_events': 0, 'reasoning_effort': reasoning_effort}
    finally:
        primary_failure = sys.exc_info()[0] is not None
        if not complete and assistant_message_id:
            try:
                client.call('POST', session_path + '/stop', {'message_id': assistant_message_id})
            except Exception:
                # Cancellation is best effort; deletion must still happen and
                # neither cleanup operation may hide the original failure.
                pass
        try:
            client.call('DELETE', session_path)
        except Exception:
            if not primary_failure:
                raise RuntimeError('Native stream test session cleanup failed; response omitted') from None
