#!/usr/bin/env python3
"""Configure the upstream product through its public APIs; no application fork."""
import argparse
import json
from pathlib import Path
import time
import traceback

from common import ROOT, Client, ApiError, read_env, save_json, wait_health


def identity(client, root):
    state = json.loads((root / 'admin.json').read_text())
    try:
        login = client.login(state)
    except ApiError as exc:
        if exc.status not in (400, 401):
            raise
        client.call('POST', '/auth/register', {k: state[k] for k in ('email', 'username', 'password')})
        login = client.login(state)
    tenant = login.get('active_tenant') or login.get('tenant') or {}
    state['tenant_id'] = tenant.get('id') or login['user']['tenant_id']
    save_json(root / 'admin.json', state)
    return state


def model_payload(env):
    for key in ('LLM_BASE_URL', 'LLM_MODEL', 'LLM_API_KEY'):
        if not env.get(key):
            raise ValueError('Existing server model configuration is incomplete')
    if env['LLM_BASE_URL'].rstrip('/') != 'https://ark.cn-beijing.volces.com/api/v3':
        raise ValueError('Unexpected model endpoint; review before sending its credential')
    compat = {'max_tokens_field': 'max_tokens', 'supports_temperature': True,
              'fixed_temperature': float(env.get('LLM_TEMPERATURE', '0.6')),
              'supports_reasoning_effort': False,
              'extra_body': {'thinking': {'type': 'disabled'}}}
    if env['LLM_MODEL'] == 'kimi-k3-1-pro-261024':
        # Ark requires 1 in thinking mode and 0.6 otherwise. Its defaults
        # handle both, including native agents that override thinking per turn.
        compat['supports_temperature'] = False
        compat.pop('fixed_temperature')
    return {'name': env['LLM_MODEL'], 'display_name': '火山 Kimi', 'type': 'KnowledgeQA',
            'source': 'remote', 'parameters': {
                'base_url': env['LLM_BASE_URL'].rstrip('/'), 'api_key': env['LLM_API_KEY'],
                'provider': 'volcengine', 'max_concurrency': 8,
                'spec': {'api': 'openai-completions', 'reasoning': False,
                         'compat': compat}}}


def kb_payload(name, embedding, chat):
    return {'name': name, 'type': 'document', 'embedding_model_id': embedding,
            'summary_model_id': chat,
            'indexing_strategy': {'vector_enabled': True, 'keyword_enabled': True,
                                  'wiki_enabled': True, 'graph_enabled': False},
            # This is a real native pipeline: questions/summaries have a model,
            # unlike the old integration's per-upload disabling workaround.
            'question_generation_config': {'enabled': True, 'question_count': 3},
            'chunking_config': {'chunk_size': 1024, 'chunk_overlap': 128},
            'wiki_config': {'synthesis_model_id': chat, 'max_pages_per_ingest': 20,
                            'extraction_granularity': 'focused', 'ingest_batch_size': 2,
                            'ingest_map_parallel': 1, 'ingest_reduce_parallel': 1,
                            'ingest_max_inflight': 1,
                            'content_instructions': '使用中文，保留来源与日期，区分负责人、参与人、待确认内容和冲突。',
                            'extraction_instructions': '整理项目、芯片型号及版本、模块、明确的人员分工和设计决策。不要将参会或提及推断为负责。'}}


def ensure_model(client, payload):
    found = next((m for m in client.call('GET', '/models')['data']
                  if m['name'] == payload['name'] and m['type'] == payload['type']), None)
    if not found:
        found = client.call('POST', '/models', payload)['data']
    deadline = time.monotonic() + 180
    while found.get('status') != 'active' and time.monotonic() < deadline:
        if found.get('status') == 'download_failed':
            raise RuntimeError('Native model activation failed; inspect the model settings')
        time.sleep(2)
        found = client.call('GET', '/models/' + found['id'])['data']
    if found.get('status') != 'active':
        raise RuntimeError('Model activation did not finish')
    return found['id']


def configure(client, root, llm_env):
    state = identity(client, root)
    if state.get('configured'):
        return state
    client.call('PUT', '/tenants/' + str(state['tenant_id']), {'name': '企业研发知识空间'})
    embed = ensure_model(client, {'name': 'qwen3-embedding:0.6b', 'display_name': '本地向量模型',
        'type': 'Embedding', 'source': 'local', 'parameters': {'base_url': 'http://embedding:11434',
        'embedding_parameters': {'dimension': 1024, 'truncate_prompt_tokens': 8192}, 'max_concurrency': 1}})
    chat = ensure_model(client, model_payload(read_env(llm_env)))
    client.call('PUT', '/tenants/kv/default-settings', {
        'chat_model_id': chat, 'utility_model_id': chat, 'embedding_model_id': embed,
        'rerank_model_id': '', 'vlm_model_id': '', 'asr_model_id': ''})
    client.call('PUT', '/tenants/kv/assistant-config', {'display_name': '知识维护助手', 'max_access_level': 'confirm'})
    client.call('PUT', '/tenants/kv/memory-config', {'enabled': False})
    providers = client.call('GET', '/web-search-providers')['data']
    provider = next((p for p in providers if p['name'] == '内置 SearXNG'), None)
    if not provider:
        provider = client.call('POST', '/web-search-providers', {'name': '内置 SearXNG',
            'provider': 'searxng', 'parameters': {'base_url': 'http://searxng:8080'}, 'is_default': True})['data']
    kb = next((k for k in client.call('GET', '/knowledge-bases')['data'] if k['name'] == '企业公共知识'), None)
    if not kb:
        kb = client.call('POST', '/knowledge-bases', kb_payload('企业公共知识', embed, chat))['data']
    agent_ids = {}
    agents = client.call('GET', '/agents')['data']
    for name, config in [
        ('芯片调研', {'kb_selection_mode': 'none', 'allowed_tools': [], 'web_search_enabled': True,
                     'system_prompt': '用中文帮助用户梳理芯片需求。每轮追问最关键的1到3个问题，允许修正；自行判断何时开始调研。条件不足时明确假设。优先查官方产品页和数据手册，给出3到5个候选的参数对比、适配理由、风险和来源链接。查不到的参数明确标为未知，不编造。搜索仅使用必要技术条件，不发送内部项目名、人员信息或内部原文。'}),
        ('企业知识问答', {'kb_selection_mode': 'all', 'web_search_enabled': False,
                     'allowed_tools': ['search_knowledge', 'read_document', 'list_documents', 'wiki_search', 'wiki_read_page'],
                     'system_prompt': '用中文依据企业源文档和Wiki回答，给出来源。负责人和芯片版本优先核对原文，区分已确认、推测、冲突和时间。没有资料时明确说明。需要新增或修改源资料时引导用户使用知识维护助手或知识库界面。'})]:
        found = next((a for a in agents if a['name'] == name and not a.get('is_builtin')), None)
        if not found:
            config.update({'agent_mode': 'smart-reasoning', 'agent_type': 'custom', 'model_id': chat,
                           'temperature': 0.6, 'max_iterations': 16, 'multi_turn_enabled': True,
                           'mcp_selection_mode': 'none', 'skills_selection_mode': 'none',
                           'memory_enabled': False, 'access_level': 'read_only'})
            found = client.call('POST', '/agents', {'name': name, 'config': config})['data']
        agent_ids[name] = found['id']
    state.update(embedding_model_id=embed, chat_model_id=chat, kb_id=kb['id'],
                 search_provider_id=provider['id'], agents=agent_ids, configured=True)
    save_json(root / 'admin.json', state)
    return state


def open_team_registration(client, root):
    state = identity(client, root)
    if not state.get('invitation'):
        state['invitation'] = client.call('POST', f"/tenants/{state['tenant_id']}/invite-links",
            {'role': 'contributor', 'message': '加入企业研发知识空间，自行注册后即可使用。'})['data']
        save_json(root / 'admin.json', state)
    # The bootstrap account has been promoted by the app restart in apply.sh.
    client.call('PUT', '/system/admin/settings/auth.registration_mode', {'value': 'invite_register'})
    effective = client.call('GET', '/auth/config')
    # Keep the exact returned shape for local administration, with no credentials.
    save_json(root / 'auth-config.json', effective)
    state['team_registration_configured'] = True
    save_json(root / 'admin.json', state)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('identity', 'configure', 'team'))
    parser.add_argument('--llm-env', type=Path, default=Path('/data/solexai/yongjun/select-chip-agent/.env'))
    args = parser.parse_args()
    try:
        wait_health()
        client = Client()
        if args.action == 'identity':
            identity(client, ROOT)
        elif args.action == 'configure':
            configure(client, ROOT, args.llm_env)
        else:
            open_team_registration(client, ROOT)
        print('Native configuration phase completed: ' + args.action)
    except (ValueError, RuntimeError, KeyError, OSError) as exc:
        if isinstance(exc, (RuntimeError, ValueError)):
            raise SystemExit(str(exc)) from None
        frame = traceback.extract_tb(exc.__traceback__)[-1]
        raise SystemExit(f'Native configuration failed: {type(exc).__name__} at '
                         f'{Path(frame.filename).name}:{frame.lineno} ({frame.name}); '
                         'credential details omitted') from None
