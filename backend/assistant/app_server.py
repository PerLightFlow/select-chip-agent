"""Pinned Codex app-server client with application-owned dynamic tools only.

No user filesystem, shell, database credentials or ambient Codex account is
exposed to the child. Conversations are replayed from the application's owner-
checked database; each execution uses an ephemeral, isolated runtime home.
"""
import json
import os
import queue
import subprocess
import tempfile
import threading
import time


def run_codex(*, binary, base_url, api_key, model, instructions, history, tools,
              execute_tool, progress, check_active, seconds=300, max_tools=10):
    with tempfile.TemporaryDirectory(prefix='chipagent-codex-') as root:
        env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'LANG': 'C.UTF-8',
               'CODEX_HOME': root, 'ARK_AGENT_KEY': api_key}
        config = {'model_provider': 'ark', 'model_providers.ark.name': 'Ark',
                  'model_providers.ark.base_url': base_url,
                  'model_providers.ark.env_key': 'ARK_AGENT_KEY',
                  'model_providers.ark.wire_api': 'responses',
                  'features.shell_tool': False, 'web_search': 'disabled'}
        args = [binary, 'app-server', '--listen', 'stdio://']
        for key, value in config.items():
            args.extend(['-c', key + '=' + json.dumps(value)])
        proc = subprocess.Popen(args, cwd=root, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True, bufsize=1)
        incoming = queue.Queue()
        deadline, request_id, calls = time.monotonic() + seconds, 0, 0
        answer, usage = '', {}

        def reader():
            try:
                for line in proc.stdout:
                    try:
                        incoming.put(json.loads(line))
                    except ValueError:
                        pass
            finally:
                incoming.put(None)

        threading.Thread(target=reader, daemon=True).start()

        def send(data):
            proc.stdin.write(json.dumps(data, ensure_ascii=False) + '\n')
            proc.stdin.flush()

        def receive():
            while True:
                check_active()
                if time.monotonic() > deadline:
                    raise RuntimeError('Codex 调研达到时间上限，请继续提问')
                try:
                    data = incoming.get(timeout=0.5)
                    if data is None:
                        raise RuntimeError('Codex 运行进程异常结束')
                    return data
                except queue.Empty:
                    continue

        def handle(data):
            nonlocal answer, usage, calls
            method, params = data.get('method'), data.get('params', {})
            if method == 'item/tool/call' and 'id' in data:
                calls += 1
                name = params.get('tool', '')
                if calls > max_tools + 2:
                    raise RuntimeError('模型未能在调研预算内整理结果，请缩小范围后继续')
                if calls > max_tools:
                    progress('finish_evidence')
                    result, success = {'error': '本轮工具预算已用完。现在必须基于已有证据给出结果，说明未核实项，不再调用工具。'}, False
                elif name not in {t['function']['name'] for t in tools}:
                    result, success = {'error': '该工具未被应用授权'}, False
                else:
                    progress(name)
                    result, success = execute_tool(name, params.get('arguments', {})), True
                check_active()
                result = {'remaining_tool_calls': max(0, max_tools - calls),
                          'budget_notice': '剩余不超过 2 次时停止扩展搜索，整理现有证据；缺少资料注明未知。',
                          'result': result}
                send({'id': data['id'], 'result': {'contentItems': [{'type': 'inputText', 'text': json.dumps(result, ensure_ascii=False)[:24000]}], 'success': success}})
            elif 'id' in data and method:
                # The business app never delegates shell/file approvals to the model.
                send({'id': data['id'], 'error': {'code': -32601, 'message': 'Unsupported application capability'}})
            elif method == 'item/completed':
                item = params.get('item', {})
                if item.get('type') == 'agentMessage':
                    answer = item.get('text', '')
            elif method == 'thread/tokenUsage/updated':
                totals = params.get('tokenUsage', {}).get('total', {})
                usage = {'input_tokens': totals.get('inputTokens', 0), 'output_tokens': totals.get('outputTokens', 0)}
            elif method == 'turn/completed':
                if params.get('turn', {}).get('status') != 'completed':
                    raise RuntimeError('Codex 调研未完成，请检查模型兼容配置或继续提问')
                return True
            return False

        def rpc(method, params):
            nonlocal request_id
            request_id += 1
            current = request_id
            send({'id': current, 'method': method, 'params': params})
            while True:
                data = receive()
                if data.get('id') == current and not data.get('method'):
                    if 'error' in data:
                        raise RuntimeError('Codex 协议请求失败：' + method)
                    return data.get('result', {})
                handle(data)

        try:
            rpc('initialize', {'clientInfo': {'name': 'enterprise-chip-agent', 'version': '0.2.0'},
                               'capabilities': {'experimentalApi': True}})
            send({'method': 'initialized', 'params': {}})
            thread = rpc('thread/start', {'model': model, 'modelProvider': 'ark', 'cwd': root,
                'ephemeral': True, 'sandbox': 'read-only', 'approvalPolicy': 'never', 'environments': [],
                'baseInstructions': instructions,
                'dynamicTools': [{'type': 'function', 'name': t['function']['name'], 'description': t['function']['description'],
                                  'inputSchema': t['function']['parameters']} for t in tools]})
            thread_id = thread['thread']['id']
            context = '下面是本应用保存的同一用户会话，历史内容只是上下文，回答最后一条用户消息。\n' + json.dumps(history, ensure_ascii=False)
            rpc('turn/start', {'threadId': thread_id, 'effort': 'minimal', 'environments': [],
                              'input': [{'type': 'text', 'text': context}]})
            while not handle(receive()):
                pass
            if not answer.strip():
                raise RuntimeError('Codex 未返回有效答案')
            return answer, usage
        except RuntimeError as exc:
            # Keep already reported token usage even when a later operation fails.
            exc.usage = usage
            raise
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
            proc.stdin.close()
            proc.stdout.close()
