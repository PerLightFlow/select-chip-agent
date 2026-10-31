#!/usr/bin/env python3
"""Provision an isolated WeKnora integration tenant. Saves credentials only to --state.

Run against the loopback admin endpoint after pulling qwen3-embedding:0.6b.
Uses only Python stdlib, never logs API response bodies or passwords.
"""
import argparse
import json
from pathlib import Path
import secrets
from urllib import request, error, parse

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:18081')
parser.add_argument('--state', required=True, type=Path)
parser.add_argument('--scope', default='common')
args = parser.parse_args()
if parse.urlsplit(args.url).hostname not in ('127.0.0.1', 'localhost'):
    raise SystemExit('Bootstrap only supports a loopback endpoint (use SSH forwarding if needed)')
state_path = args.state.resolve()
state_path.parent.mkdir(parents=True, exist_ok=True)
state = json.loads(state_path.read_text()) if state_path.exists() else {
    'email': f'chipagent-{secrets.token_hex(6)}@integration.invalid',
    'username': f'chipagent-{secrets.token_hex(6)}', 'password': 'Aa1' + secrets.token_urlsafe(18),
    'url': args.url, 'collections': {}}
if state.get('url') != args.url:
    raise SystemExit('State belongs to another endpoint')


def save():
    temporary = state_path.with_suffix('.pending')
    temporary.touch(mode=0o600, exist_ok=True)
    temporary.chmod(0o600)
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    temporary.replace(state_path)


save()  # Preserve identity before registration so an interrupted run can log in.
opener = request.build_opener(request.ProxyHandler({}))
token = ''


def api(method, path, payload=None, allowed=(), api_key=None):
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['X-API-Key'] = api_key
    elif token:
        headers['Authorization'] = 'Bearer ' + token
    req = request.Request(args.url + '/api/v1' + path,
        data=json.dumps(payload).encode() if payload is not None else None, headers=headers, method=method)
    try:
        with opener.open(req, timeout=60) as response:
            result = json.load(response)
        if result.get('success') is not True:
            raise SystemExit(f'{method} {path}: operation unsuccessful (response omitted)')
        return result
    except error.HTTPError as exc:
        if exc.code in allowed:
            return None
        raise SystemExit(f'{method} {path}: HTTP {exc.code} (response omitted)') from None


login = api('POST', '/auth/login', {'email': state['email'], 'password': state['password']}, allowed=(400, 401))
if login is None:
    password = state['password']
    if not (8 <= len(password) <= 32 and any(c.isalpha() for c in password) and any(c.isdigit() for c in password)):
        # Earlier bootstrap versions saved an oversized password before registration.
        # Only repair after login fails; existing authenticated accounts are untouched.
        state['password'] = 'Aa1' + secrets.token_urlsafe(18)
        save()
    api('POST', '/auth/register', {k: state[k] for k in ('username', 'email', 'password')})
    login = api('POST', '/auth/login', {'email': state['email'], 'password': state['password']})
token = login['token']
tenant = login.get('active_tenant') or login.get('tenant') or {}
tenant_id = tenant.get('id') or login['user']['tenant_id']
state['tenant_id'] = tenant_id
models = api('GET', '/models')['data']
model = next((m for m in models if m['name'] == 'qwen3-embedding:0.6b' and m['type'] == 'Embedding'), None)
if model is None:
    model = api('POST', '/models', {'name': 'qwen3-embedding:0.6b', 'display_name': '企业知识本地向量模型',
        'type': 'Embedding', 'source': 'local', 'parameters': {'base_url': 'http://embedding:11434',
        'embedding_parameters': {'dimension': 1024, 'truncate_prompt_tokens': 8192}, 'max_concurrency': 1}})['data']
state['embedding_model_id'] = model['id']
save()
name = 'select-chip-agent/' + args.scope
collections = api('GET', '/knowledge-bases')['data']
kb = next((k for k in collections if k['name'] == name), None)
if kb is None:
    kb = api('POST', '/knowledge-bases', {'name': name, 'type': 'document',
        'embedding_model_id': model['id'],
        'indexing_strategy': {'vector_enabled': True, 'keyword_enabled': True, 'wiki_enabled': False, 'graph_enabled': False},
        'question_generation_config': {'enabled': True, 'question_count': 3},
        'chunking_config': {'chunk_size': 1024, 'chunk_overlap': 128}})['data']
# v0.9.0's KB-level question-off filter produces unsupported ParadeDB SQL.
# Keep that retrieval filter off, but EVERY application upload explicitly sets
# process_config.question_generation_config.enabled=false (no chat model exists).
# Only this application may ingest into the dedicated tenant; do not use its UI
# for unmanaged uploads. The live probe separately checks vector and keyword recall.
api('PATCH', '/knowledge-bases/' + kb['id'], {'question_generation_config': {'enabled': True, 'question_count': 3}})
state['collections'][args.scope] = kb['id']
save()
ids = list(state['collections'].values())
for role, capabilities in [('read', ['retrieve']), ('write', ['retrieve', 'ingest'])]:
    keys = api('GET', f'/tenants/{tenant_id}/api-keys')['data']
    name = 'select-chip-agent-' + role
    key = next((k for k in keys if k['name'] == name), None)
    # v0.9.0 rejects knowledge_ids whenever a key has a KB allow-list. Retrieval
    # therefore uses a retrieve-only key within this dedicated integration tenant;
    # Django supplies/rechecks immutable published document IDs on every search.
    # Ingestion remains KB-restricted. Never grant full_access to either key.
    payload = {'name': name, 'full_access': False, 'knowledge_base_ids': ids if role == 'write' else [],
               'capabilities': capabilities}
    if key:
        # List responses are decrypted after database reads. A write response's
        # api_key may still contain its encrypted storage value; never use it.
        credential = key.get('api_key') or state.get(role + '_key')
        api('PUT', f"/tenants/{tenant_id}/api-keys/{key['id']}", payload)
    else:
        key = api('POST', f'/tenants/{tenant_id}/api-keys', payload)['data']
        credential = key.get('token')
    if not credential:
        raise SystemExit('Key value unavailable; inspect the existing credential state')
    state[role + '_key'] = credential
    api('GET', '/knowledge-bases/' + kb['id'], api_key=credential)
    save()
print(json.dumps({'scope': args.scope, 'kb_id': kb['id'], 'embedding_model_id': model['id'],
                  'credentials_saved': True, 'wiki_enabled': False}, ensure_ascii=False))
