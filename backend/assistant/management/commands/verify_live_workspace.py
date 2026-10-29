"""Real provider/search acceptance through the persistent worker, isolated DB only."""
import json
import time
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from assistant.models import Conversation, Message, Turn, KnowledgeDocument, KnowledgeVersion
from assistant.knowledge import propose, confirm_proposal, index_document, confirm_document


class Command(BaseCommand):
    help = '在隔离数据库中验证真实模型、多轮需求、企业问答与并发调研；会使用模型额度'

    def add_arguments(self, parser):
        parser.add_argument('--concurrency', type=int, default=1)
        parser.add_argument('--output', required=True)
        parser.add_argument('--scenario', choices=['workflow', 'research'], default='workflow')

    def handle(self, *args, **options):
        if not settings.DATABASES['default']['NAME'].endswith('_benchmark'):
            raise CommandError('只允许在以 _benchmark 结尾的隔离数据库运行')
        count = options['concurrency']
        if not 1 <= count <= 50:
            raise CommandError('并发必须为 1–50')
        users = list(get_user_model().objects.order_by('id')[:count])
        if len(users) != count:
            raise CommandError('请先运行 benchmark_workspace 准备账号和合成资料')
        report = {'kind': 'live_provider_and_search', 'runtime': settings.AGENT_RUNTIME,
                  'scenario': options['scenario'], 'requested_concurrency': count,
                  'model': settings.LLM_MODEL, 'rounds': [], 'passed': False}

        def save():
            Path(options['output']).write_text(json.dumps(report, ensure_ascii=False, indent=2))

        def submit(conversation, text):
            Message.objects.create(conversation=conversation, role='user', content=text)
            return Turn.objects.create(conversation=conversation)

        def await_turns(turns, require_sources=False):
            ids = [t.pk for t in turns]
            start, peak = time.monotonic(), 0
            deadline = start + settings.AGENT_TURN_SECONDS + 90
            while time.monotonic() < deadline:
                close_old_connections()
                pending = Turn.objects.filter(pk__in=ids, state__in=['queued', 'running'])
                peak = max(peak, pending.filter(state='running').count())
                if not pending.exists():
                    break
                time.sleep(0.5)
            Turn.objects.filter(pk__in=ids, state__in=['queued', 'running']).update(state='cancelled', error='验收等待超时')
            results = []
            for turn in Turn.objects.filter(pk__in=ids).select_related('conversation').order_by('created_at'):
                answer = turn.conversation.messages.filter(role='assistant', created_at__gte=turn.created_at).order_by('-id').first()
                verified = sum(s.get('kind') == 'source_text' for s in answer.sources) if answer else 0
                comparison = bool(answer and len(answer.content) >= 500 and '|' in answer.content
                                  and all(model in answer.content for model in ['ESP32-P4','STM32N6','RK3568'])
                                  and any(s.get('kind') == 'source_text' and s['url'] in answer.content for s in answer.sources))
                events = turn.events
                began = events[0]['at'] if events else None
                results.append({'id': str(turn.pk), 'state': turn.state, 'error': turn.error,
                    'created_at': turn.created_at.isoformat(), 'first_progress_at': began,
                    'seconds': round((turn.updated_at-turn.created_at).total_seconds(), 2),
                    'usage': turn.usage, 'verified_sources': verified,
                    'tool_events': [e['text'] for e in events],
                    'sources': answer.sources if answer else [],
                    'answer': answer.content if answer else '',
                    'brief': turn.conversation.brief,
                    'comparison_delivered': comparison if require_sources else None,
                    'ok': turn.state == 'done' and bool(answer) and (not require_sources or (verified > 0 and comparison))})
            durations = sorted(r['seconds'] for r in results)
            record = {'count': len(results), 'success': sum(r['ok'] for r in results), 'peak_running_tasks': peak,
                      'wall_seconds': round(time.monotonic()-start, 2),
                      'p50_seconds': durations[len(durations)//2],
                      'p95_seconds': durations[min(len(durations)-1, int(len(durations)*.95))],
                      'results': results}
            report['rounds'].append(record); save()
            self.stdout.write(json.dumps({k:v for k,v in record.items() if k!='results'}, ensure_ascii=False))
            return all(r['ok'] for r in results)

        if options['scenario'] == 'workflow':
            conversation = Conversation.objects.create(owner=users[0], title='隔离验收：连续需求')
            first = await_turns([submit(conversation, '我想做一个带屏、离线运行算法的视觉检测设备，还没选芯片。请先帮我梳理需求。')])
            if first:
                second = await_turns([submit(conversation, '用于简单分类，1 路摄像头，5 寸触摸屏，每秒 5 帧即可，插电供电，平台成本目标 200 元，优先开源 SDK。请联网比较 ESP32-P4、STM32N6 和 RK3568，核实官方资料，不能确认的性能注明待实测。')], True)
                third = await_turns([submit(conversation, '修正刚才条件：不要 Linux，只考虑 RTOS 或裸机。请更新需求摘要，简要说明前面候选如何变化。')])
                conversation.refresh_from_db()
                correction = 'Linux' in conversation.brief and any(x in conversation.brief for x in ['RTOS', '裸机'])
            else:
                second = third = correction = False
            # The fixture is explicitly synthetic and exists only in this isolated database.
            doc = KnowledgeDocument.objects.create(owner=users[0], title='验收项目 A：合成设计记录')
            version = KnowledgeVersion.objects.create(document=doc, revision=1, state='indexing',
                text='这是合成验收资料。验收项目 A 图像采集模块使用 ESP32-P4，硬件组测试甲负责电路设计，软件组测试乙参与驱动开发。')
            index_document(version.pk); confirm_document(version.pk, users[0])
            data = {'code':'ACCEPTANCE-A','name':'验收项目 A','aliases':['合成采集项目'], 'summary':'合成测试资料',
                    'modules':[{'name':'图像采集','chips':['ESP32-P4'],
                      'responsible':[{'name':'测试甲','department':'硬件组','work':'电路设计'}],
                      'participants':[{'name':'测试乙','department':'软件组','work':'驱动开发'}],'notes':''}],
                    'document_ids':[doc.pk],'evidence_note':'隔离数据库中的合成资料','effective_from':'2026-01-01'}
            confirm_proposal(propose(users[0], data).pk, users[0])
            knowledge = Conversation.objects.create(owner=users[-1], title='隔离验收：项目问答')
            fourth = await_turns([submit(knowledge, '验收项目 A 用了什么芯片，图像采集部分是谁做的？请查项目卡片及依据文档，区分负责人和参与人。')])
            answer = knowledge.messages.filter(role='assistant').last()
            document_url = f'/api/assistant/documents/{doc.pk}/file/?version={version.pk}'
            document_cited = bool(answer and document_url in answer.content
                                  and any(s.get('url') == document_url for s in answer.sources))
            project_cited = bool(answer and any(s.get('kind') == 'project_record' and s.get('url') in answer.content
                                                for s in answer.sources))
            grounded = bool(answer and all(x in answer.content for x in ['ESP32-P4','测试甲','测试乙'])
                            and document_cited and project_cited)
            report.update(passed=first and second and third and correction and fourth and grounded,
                          correction_remembered=correction, knowledge_answer_grounded=grounded,
                          knowledge_document_cited=document_cited, knowledge_project_cited=project_cited)
        else:
            conversations = [Conversation.objects.create(owner=u, title='隔离验收：同时联网调研') for u in users]
            prompts = ['简单图像分类','条码检测','工件有无检测','显示和图像采集','低分辨率图像分类']
            turns = [submit(c, f'我需要带屏离线视觉设备：{prompts[i % len(prompts)]}，1 路摄像头、5 寸触摸屏、5 FPS、插电供电，芯片平台目标 200 元、开放 SDK。现在开始联网调研，比较 ESP32-P4、STM32N6、RK3568 三种候选的接口、运算条件和风险。核对官方原文，列来源链接；未知或需实测内容明确标注。') for i,c in enumerate(conversations)]
            report['passed'] = await_turns(turns, True)
        report['notice'] = '真实模型与搜索调用；自动检查完成、来源读取、摘要和关键事实，答案质量仍需人工阅读。合成资料不能代替真实企业文件分布。'
        save()
        if not report['passed']:
            raise CommandError('真实验收未全部通过，详细结果已保存；不要据此宣称容量达标')
