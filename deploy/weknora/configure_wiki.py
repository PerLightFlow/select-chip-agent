#!/usr/bin/env python3
"""Enable Wiki using server-side Ark credentials, without logging secrets."""
import argparse
import json
from pathlib import Path
from urllib import request, error, parse


def configure(state_path, llm_env, scope=None):
    state = json.loads(state_path.read_text())
    env = dict(line.split('=', 1) for line in llm_env.read_text().splitlines()
               if '=' in line and not line.lstrip().startswith('#'))
    base = state['url']
    if parse.urlsplit(base).hostname not in {'127.0.0.1', 'localhost'}:
        raise ValueError('Wiki administration must use the loopback endpoint')
    if not all(env.get(k) for k in ('LLM_BASE_URL', 'LLM_MODEL', 'LLM_API_KEY')):
        raise ValueError('Server model configuration is incomplete')
    opener = request.build_opener(request.ProxyHandler({}))
    token = ''

    def api(method, path, data=None, form=False):
        headers = {'Content-Type': 'application/x-www-form-urlencoded' if form else 'application/json',
                   'Accept-Language': 'zh-CN'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        body = (parse.urlencode(data).encode() if form else json.dumps(data).encode()) if data is not None else None
        try:
            with opener.open(request.Request(base + '/api/v1' + path, data=body, headers=headers, method=method), timeout=180) as response:
                result = json.load(response)
        except error.HTTPError as exc:
            try:
                failure = json.load(exc)
                message = str(failure.get('message') or failure.get('error', ''))
                for secret in (env['LLM_API_KEY'], state['password'], token):
                    if secret:
                        message = message.replace(secret, '[REDACTED]')
            except (ValueError, AttributeError):
                message = ''
            raise ValueError(f'Wiki configuration {method} {path} failed (HTTP {exc.code}): {message[:300]}') from None
        if result.get('success') is not True:
            raise ValueError('Wiki configuration response was unsuccessful')
        return result

    token = api('POST', '/auth/login', {'email': state['email'], 'password': state['password']})['token']
    models = api('GET', '/models')['data']
    existing = next((m for m in models if m['name'] == env['LLM_MODEL'] and m['type'] == 'KnowledgeQA'), None)
    if existing and existing.get('status') == 'download_failed':
        api('DELETE', '/models/' + existing['id'])
        existing = None
    payload = {'name': env['LLM_MODEL'], 'display_name': '企业 Wiki 整理', 'type': 'KnowledgeQA',
               'source': 'remote', 'parameters': {
                   'base_url': env['LLM_BASE_URL'], 'api_key': env['LLM_API_KEY'], 'provider': 'volcengine',
                   'max_concurrency': 2, 'spec': {'api': 'openai-completions', 'reasoning': False,
                       'compat': {'max_tokens_field': 'max_tokens', 'supports_temperature': True,
                                  'fixed_temperature': float(env.get('LLM_TEMPERATURE', '0.6')),
                                  'supports_reasoning_effort': False,
                                  'extra_body': {'thinking': {'type': 'disabled'}}}}}}
    if existing:
        api('PUT', '/models/' + existing['id'], payload)
        model_id = existing['id']
    else:
        model_id = api('POST', '/models', payload)['data']['id']
    probe = api('POST', '/models/' + model_id + '/debug', {
        'input': '仅回复 OK。', 'options': json.dumps({'max_tokens': 64, 'thinking': False})}, form=True)['data']
    if not probe.get('ok') or not probe.get('raw_response', {}).get('content'):
        raise ValueError('WeKnora model probe failed; provider response omitted')
    collections = state['collections']
    if scope:
        collections = {scope: collections[scope]}
    for kb in collections.values():
        api('PATCH', '/knowledge-bases/' + kb, {
            'indexing_strategy': {'vector_enabled': True, 'keyword_enabled': True, 'wiki_enabled': True, 'graph_enabled': False},
            'wiki_config': {'synthesis_model_id': model_id, 'max_pages_per_ingest': 20,
                'extraction_granularity': 'focused', 'ingest_batch_size': 2, 'ingest_map_parallel': 1,
                'ingest_reduce_parallel': 1, 'ingest_max_inflight': 1,
                'content_instructions': '使用中文。只依据资料，保留来源和日期；明确区分负责人、参与人、待确认事项和冲突。不能将参会或提及某人推断为负责。',
                'extraction_instructions': '优先整理企业项目、芯片型号及版本、模块、明确的人员分工和设计决策。不要为无关常见词创建页面。'}})
    state['wiki_model_id'] = model_id
    state['wiki_enabled'] = True
    temporary = state_path.with_suffix('.pending')
    temporary.touch(mode=0o600, exist_ok=True)
    temporary.chmod(0o600)
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    temporary.replace(state_path)
    return {'model_probe': 'passed', 'model': env['LLM_MODEL'], 'wiki_enabled': True, 'collections': len(collections)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--llm-env', type=Path, required=True)
    parser.add_argument('--scope')
    args = parser.parse_args()
    try:
        print(json.dumps(configure(args.state, args.llm_env, args.scope), ensure_ascii=False))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    except (OSError, KeyError):
        raise SystemExit('Wiki configuration failed; inspect server-side configuration without exposing credentials') from None
