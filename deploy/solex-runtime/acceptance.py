"""Managed-runtime live checks using one disposable personal workspace."""
import json
import secrets
import time
from api_client import ROOT, Client, ApiError, save_json
from stream_check import check_stream


def expect_forbidden(client, method, path, data=None):
    try:
        client.call(method, path, data)
    except ApiError as exc:
        if exc.status == 403:
            return
        raise
    raise RuntimeError('A managed configuration write was not rejected')


def acceptance_identity():
    # Match the application's complex-password policy (8-32 characters).
    return {'username': '__managed_check_' + secrets.token_hex(4),
            'email': 'managed-' + secrets.token_hex(6) + '@example.invalid',
            'password': secrets.token_urlsafe(18) + 'Aa1!'}


def run(state_dir):
    admin = Client()
    admin.login(json.loads((ROOT / 'admin.json').read_text()))
    caps = admin.call('GET', '/system/capabilities')['data']
    if not caps.get('managed_runtime'):
        raise RuntimeError('Managed runtime capability is not active')
    state = acceptance_identity()
    client = Client()
    user_id = None
    tenant_id = None
    kb_id = None
    agent_id = None
    try:
        user = client.call('POST', '/auth/register', state)['user']
        user_id = user['id']
        login = client.login(state)
        tenant_id = login['user'].get('tenant_id') or user.get('tenant_id')
        if login['user'].get('is_system_admin'):
            raise RuntimeError('Acceptance requires an ordinary user')
        models = client.call('GET', '/models')['data']
        if not models or any(not m.get('is_builtin') for m in models):
            raise RuntimeError('Ordinary model catalog must contain shared models only')
        providers = client.call('GET', '/web-search-providers')['data']
        if not providers: raise RuntimeError('System web search provider was not inherited')
        defaults = client.call('GET', '/tenants/kv/default-settings')['data']
        if not defaults.get('chat_model_id') or not defaults.get('embedding_model_id'):
            raise RuntimeError('Ordinary user did not inherit configured defaults')
        for path in ['/models', '/mcp-services', '/web-search-providers', '/system/sandbox-check', '/system/parser-engines/check']:
            expect_forbidden(client, 'POST', path, {})
        expect_forbidden(client, 'PUT', '/tenants/kv/default-settings', {})
        expect_forbidden(client, 'PUT', '/models/' + defaults['chat_model_id'], {})
        # No model ID, endpoint or credential in either request.
        agent = client.call('POST', '/agents', {'name': '__managed_acceptance__',
            'description': 'Synthetic acceptance only', 'config': {'agent_mode':'quick-answer',
            'system_prompt':'只需简短回答用户的问题。', 'kb_selection_mode':'none'}})['data']
        agent_id = agent['id']
        kb = client.call('POST', '/knowledge-bases', {'name':'__managed_acceptance__',
            'description':'Synthetic acceptance only', 'type':'document', 'wiki_config':{'enabled':False}, 'profile_config':{'enabled':False}, 'auto_tag_config':{'enabled':False}})['data']
        kb_id = kb['id']
        if kb.get('embedding_model_id') != defaults['embedding_model_id']:
            raise RuntimeError('New knowledge base did not inherit embedding default')
        if kb.get('summary_model_id') != defaults['chat_model_id']:
            raise RuntimeError('New knowledge base did not inherit generation default')
        document = client.call('POST', '/knowledge-bases/' + kb_id + '/knowledge/file',
            upload=('managed-acceptance.md', '# 合成验收资料\n\n测试项目使用 ESP32-P4 芯片，测试甲负责采集电路。\n'.encode()))['data']
        doc_id = document['id']
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            parsed = client.call('GET', '/knowledge/' + doc_id)['data']
            if parsed.get('parse_status') == 'failed': raise RuntimeError('Ordinary document indexing failed')
            if parsed.get('parse_status') == 'completed': break
            time.sleep(2)
        else: raise RuntimeError('Ordinary document indexing timed out')
        hits = client.call('POST', '/knowledge-search', {'query':'ESP32-P4 采集电路',
            'knowledge_ids':[doc_id], 'match_count':5, 'disable_vector_match':False,
            'disable_keywords_match':True, 'rerank':{'enabled':False}})['data']
        if not hits or not any('ESP32-P4' in hit.get('content','') for hit in hits):
            raise RuntimeError('Ordinary shared-embedding vector retrieval failed')
        # Shared runtime must not imply shared private agents or knowledge bases.
        other_agents = admin.call('GET', '/agents')['data']
        if isinstance(other_agents, dict):
            other_agents = other_agents.get('items', other_agents.get('agents', []))
        if any(a.get('id') == agent_id for a in other_agents):
            raise RuntimeError('Personal agent appeared in the admin workspace')
        other_kbs = admin.call('GET', '/knowledge-bases')['data']
        if any(k.get('id') == kb_id for k in other_kbs):
            raise RuntimeError('Personal knowledge base appeared in the admin workspace')
        chat = check_stream(client, agent_id=agent_id)
        result = {'passed': True, 'time': time.time(), 'ordinary_registration': True,
            'default_models_inherited': True, 'search_provider_inherited': True, 'configuration_writes_forbidden': True,
            'create_agent_without_model': True, 'create_kb_without_model': True, 'ordinary_upload_and_vector_retrieval':True,
            'personal_workspace_list_isolation': True, 'chat_stream': chat,
            'capacity_tested': False}
        save_json(state_dir / 'acceptance.json', result)
        return result
    finally:
        cleanup_errors = []
        for path in ([('/knowledge-bases/' + kb_id)] if kb_id else []) + ([('/agents/' + agent_id)] if agent_id else []):
            try: client.call('DELETE', path)
            except Exception: cleanup_errors.append(path.split('/')[1])
        if user_id:
            try: admin.call('POST', '/system/admin/users/status', {'user_id':user_id, 'is_active':False})
            except Exception: cleanup_errors.append('test-account-disable')
        save_json(state_dir / 'test-identity.json', {'user_id':user_id, 'tenant_id':tenant_id,
            'test_account_disabled':user_id is not None and 'test-account-disable' not in cleanup_errors,
            'cleanup_errors':cleanup_errors})
        if cleanup_errors:
            raise RuntimeError('Synthetic acceptance cleanup failed; see protected receipt')
