#!/usr/bin/env python3
"""Small live gate on synthetic data. Does not claim capacity or research QA."""
from html.parser import HTMLParser
import json
import time
from urllib import request

from common import ROOT, Client, ApiError, save_json, wait_health
from bootstrap import identity, kb_payload
from stream_check import check_stream


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if tag == 'script' and fields.get('src', '').startswith('/assets/'):
            self.scripts.append(fields['src'])


def check_ui(base):
    opener = request.build_opener(request.ProxyHandler({}))
    with opener.open(base + '/', timeout=15) as response:
        html = response.read().decode()
    parser = Assets()
    parser.feed(html)
    if not parser.scripts:
        raise RuntimeError('Native frontend contains no compiled application assets')
    for path in parser.scripts:
        with opener.open(base + path, timeout=15) as response:
            if 'html' in response.headers.get('Content-Type', '') or not response.read(128):
                raise RuntimeError('Native frontend asset delivery failed')
    with opener.open(base + '/api/v1/auth/config', timeout=15) as response:
        if not isinstance(json.load(response), dict):
            raise RuntimeError('Frontend API proxy failed')


def wiki_payload(result):
    # Wiki handlers return raw objects in v0.9.0, unlike most API envelopes.
    return result.get('data', result)


def run():
    wait_health()
    check_ui('http://127.0.0.1:18082')
    client = Client()
    state = identity(client, ROOT)
    model = client.call('POST', '/models/' + state['chat_model_id'] + '/debug',
        {'input': '仅回复 OK。', 'options': json.dumps({'max_tokens': 64, 'thinking': False})}, form=True)['data']
    if not model.get('ok') or not model.get('raw_response', {}).get('content'):
        raise RuntimeError('Kimi model probe failed; provider response omitted')
    stream_checks = [check_stream(client, state['chat_model_id'], effort) for effort in (None, 'off')]
    client.call('POST', '/web-search-providers/' + state['search_provider_id'] + '/test')
    # A dedicated disposable KB retains failure evidence for the next retry.
    smoke_path = ROOT / 'smoke-state.json'
    smoke = json.loads(smoke_path.read_text()) if smoke_path.exists() else {}
    if not smoke.get('kb_id'):
        name = '__native_acceptance__'
        kb = next((k for k in client.call('GET', '/knowledge-bases')['data'] if k['name'] == name), None)
        if not kb:
            kb = client.call('POST', '/knowledge-bases', kb_payload(
                name, state['embedding_model_id'], state['chat_model_id']))['data']
        smoke['kb_id'] = kb['id']
        save_json(smoke_path, smoke)
    kb_id = smoke['kb_id']
    if not smoke.get('document_id'):
        filename = 'native-acceptance.md'
        # Find an upload accepted before an interrupted response, instead of
        # generating an unbounded sequence of duplicate synthetic documents.
        docs = client.call('GET', '/knowledge-bases/' + kb_id + '/knowledge')['data']
        if isinstance(docs, dict):
            docs = docs.get('items', docs.get('data', []))
        found = next((d for d in docs if d.get('file_name') == filename), None)
        if found is None:
            found = client.call('POST', '/knowledge-bases/' + kb_id + '/knowledge/file', upload=(filename,
                '# 原生切换验收\n\n这是一份合成测试资料，不是真实项目。\n视觉检测设备采用 ESP32-P4 芯片。测试甲负责采集电路，测试乙负责摄像头驱动。\n'.encode()))['data']
        smoke['document_id'] = found['id']
        save_json(smoke_path, smoke)
    doc_id = smoke['document_id']
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        doc = client.call('GET', '/knowledge/' + doc_id)['data']
        stats = wiki_payload(client.call('GET', '/knowledgebase/' + kb_id + '/wiki/stats'))
        if doc.get('parse_status') == 'failed':
            raise RuntimeError('Native upload parsing failed; old application is still running')
        if (doc.get('parse_status') == 'completed' and stats.get('total_pages', 0) > 0
                and stats.get('pending_tasks', 0) == 0 and not stats.get('is_active', False)):
            break
        time.sleep(5)
    else:
        raise RuntimeError('Native indexing/Wiki did not complete within 15 minutes; no cutover')
    for mode in ('vector', 'keyword'):
        hits = client.call('POST', '/knowledge-search', {
            'query': 'ESP32-P4 采集 电路', 'knowledge_ids': [doc_id], 'match_count': 8,
            'disable_vector_match': mode == 'keyword', 'disable_keywords_match': mode == 'vector',
            'rerank': {'enabled': False}})['data']
        if not hits or any(h.get('knowledge_id') != doc_id for h in hits) or not any(
                'ESP32-P4' in h.get('content', '') for h in hits):
            raise RuntimeError(mode + ' native retrieval gate failed')
    page = wiki_payload(client.call('GET', '/knowledgebase/' + kb_id + '/wiki/pages/summary/' + doc_id))
    if doc_id not in json.dumps(page):
        raise RuntimeError('Generated Wiki page is missing its source reference')
    # Delete only this deployment's disposable KB; never touch user collections.
    client.call('DELETE', '/knowledge-bases/' + kb_id)
    smoke_path.unlink()
    save_json(ROOT / 'acceptance.json', {
        'passed': True, 'timestamp': time.time(), 'frontend_assets_and_proxy': True,
        'model_basic_chat': True, 'model_stream_checks': stream_checks,
        'search_provider_test': True, 'native_file_upload': True,
        'vector_retrieval': True, 'keyword_retrieval': True, 'wiki_generated_with_source': True,
        'capacity_tested': False, 'multi_user_privacy_tested': False,
        'research_quality_tested': False, 'ocr_tested': False})
    print('Native smoke gate passed: frontend, model, search, upload, two retrieval modes and Wiki.')


if __name__ == '__main__':
    try:
        run()
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        if isinstance(exc, RuntimeError):
            raise SystemExit(str(exc)) from None
        raise SystemExit('Native smoke gate failed; no cutover. Response details omitted.') from None
