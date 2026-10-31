"""Real API contract probe with synthetic text and a dedicated, explicitly supplied KB."""
import json
import time
import uuid
from types import SimpleNamespace

from django.core.management.base import BaseCommand, CommandError
from assistant.knowledge_backends.weknora import WeKnora, KnowledgeUnavailable, RemoteError


class Command(BaseCommand):
    help = '使用合成资料验证真实上传、索引、限定检索和删除；必须指定隔离验收 KB'

    def add_arguments(self, parser):
        parser.add_argument('--kb-id', required=True)
        parser.add_argument('--timeout', type=int, default=180)

    def handle(self, *args, **options):
        client, reader = WeKnora(write=True), WeKnora()
        kb = options['kb_id']
        info = client.collection(kb)
        if not info.get('name', '').startswith('select-chip-agent/acceptance'):
            raise CommandError('只允许在 acceptance 前缀的隔离知识库运行')
        strategy = info.get('indexing_strategy', {})
        if strategy.get('wiki_enabled') or strategy.get('graph_enabled'):
            raise CommandError('验收库必须关闭 Wiki 和图谱')
        replicas, ids = [], []
        delete_requested = set()
        try:
            for text in [
                '合成验收资料：视觉检测项目的图像采集模块采用 ESP32-P4 芯片，测试甲负责采集电路，测试乙负责摄像头驱动。',
                '合成验收资料：温度记录项目采用 STM32 芯片，测试丙负责温度传感器采样，不包含摄像头。',
            ]:
                r = SimpleNamespace(pk=uuid.uuid4(), collection=SimpleNamespace(remote_id=kb),
                    version=SimpleNamespace(file=None, text=text))
                replicas.append(r)
                document = client.upload(r)
                ids.append(document['id'])
            deadline = time.monotonic() + max(10, min(options['timeout'], 600))
            pending = set(ids)
            while pending and time.monotonic() < deadline:
                for remote_id in list(pending):
                    status = client.document(remote_id).get('parse_status')
                    if status == 'failed':
                        raise CommandError('合成资料的真实索引失败，请检查知识服务处理阶段')
                    if status in {'completed', 'finalizing'}:
                        pending.remove(remote_id)
                if pending:
                    time.sleep(2)
            if pending:
                raise CommandError('等待真实索引超时')
            result = reader.search('图像采集模块采用什么芯片，由谁负责电路？', [ids[0]])
            hits = result.get('data', [])
            if not hits or any(x.get('knowledge_id') != ids[0] for x in hits):
                raise CommandError('限定文档检索没有命中或超出了指定范围')
            if not any('ESP32-P4' in x.get('content', '') for x in hits):
                raise CommandError('检索片段未保留合成资料中的芯片型号')
            # Hybrid search can return HTTP 200 after one retriever fails. Test
            # each engine independently rather than mistaking partial recall for success.
            for mode in ('vector', 'keyword'):
                data = reader.request('POST', '/knowledge-search', json={
                    'query': '图像 芯片 ESP32-P4', 'knowledge_ids': [ids[0]], 'match_count': 8,
                    'disable_vector_match': mode == 'keyword',
                    'disable_keywords_match': mode == 'vector', 'rerank': {'enabled': False},
                }).get('data', [])
                if not data or any(x.get('knowledge_id') != ids[0] for x in data) or not any('ESP32-P4' in x.get('content', '') for x in data):
                    raise CommandError(f'{mode} 独立检索未通过，不能宣称混合检索正常')
            for remote_id in ids:
                client.delete(remote_id)
                delete_requested.add(remote_id)
            pending = set(ids)
            deadline = time.monotonic() + max(10, min(options['timeout'], 600))
            while pending and time.monotonic() < deadline:
                for remote_id in list(pending):
                    try:
                        client.document(remote_id)
                    except RemoteError as exc:
                        if exc.status != 404:
                            raise
                        pending.remove(remote_id)
                if pending:
                    time.sleep(2)
            if pending:
                raise CommandError('等待远端实际删除超时，删除任务已提交')
            self.stdout.write(json.dumps({'upload': 'passed', 'source_index': 'passed',
                'scoped_retrieval': 'passed', 'vector_retrieval': 'passed', 'keyword_retrieval': 'passed',
                'original_text': 'passed', 'delete': 'passed',
                'synthetic_documents': len(ids), 'wiki_tested': False}, ensure_ascii=False))
        except KnowledgeUnavailable as exc:
            raise CommandError(str(exc)) from None
        finally:
            for r in replicas:
                try:
                    found = client.find_upload(r)
                    if found and found['id'] not in delete_requested:
                        client.delete(found['id'])
                except KnowledgeUnavailable:
                    self.stderr.write('有合成验收资料需要管理员检查清理；未触及其他资料')
