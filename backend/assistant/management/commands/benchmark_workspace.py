"""Isolated database benchmark. Does NOT measure live model/search concurrency."""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.postgres.search import SearchVector
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.models import Value
from assistant.models import KnowledgeDocument, KnowledgeVersion, Passage
from assistant.knowledge import retrieve


class Command(BaseCommand):
    help = '仅在以 _benchmark 结尾的隔离数据库验证账号、文档和并发检索规模'

    def add_arguments(self, parser):
        parser.add_argument('--documents', type=int, default=10000)
        parser.add_argument('--users', type=int, default=200)
        parser.add_argument('--concurrency', type=int, default=50)

    def handle(self, *args, **options):
        if not settings.DATABASES['default']['NAME'].endswith('_benchmark'):
            raise CommandError('禁止在业务数据库执行。数据库名称必须以 _benchmark 结尾。')
        if KnowledgeDocument.objects.exists():
            raise CommandError('请使用空的隔离数据库，避免重复污染测试条件')
        count, users, workers = options['documents'], options['users'], options['concurrency']
        if not (1 <= count <= 10000 and 1 <= users <= 200 and 1 <= workers <= 50):
            raise CommandError('超出此基准的受控规模')
        start=time.monotonic()
        User=get_user_model()
        accounts=User.objects.bulk_create([User(username=f'benchmark-{i}',password='!') for i in range(users)])
        docs=KnowledgeDocument.objects.bulk_create([KnowledgeDocument(owner=accounts[i % users],title=f'合成项目资料 {i}') for i in range(count)])
        versions=KnowledgeVersion.objects.bulk_create([KnowledgeVersion(document=d,revision=1,state='published',text='合成容量测试资料') for d in docs])
        for offset in range(0,count,200):
            passages=[]
            for i,v in enumerate(versions[offset:offset+200],offset):
                for section in range(5):
                    text=f'合成项目资料 {i} 第 {section+1} 节。芯片型号 CHIP{i}，图像采集模块与接口配置。' + '仅用于数据库容量验证，包含设计条件、人员职责、芯片接口和版本说明。'*15
                    passages.append(Passage(version=v,locator=f'章节 {section+1}',text=text,
                        search_vector=SearchVector(Value(f'chip{i} 图像 采集 模块 接口 配置 项目 设计 条件 人员 职责 版本'),config='simple')))
            Passage.objects.bulk_create(passages,batch_size=500)
        build_seconds=time.monotonic()-start
        barrier=Barrier(workers)
        def task(i):
            try:
                barrier.wait(timeout=30)
                started=time.monotonic()
                found=retrieve(f'chip{i % count}')
                return {'seconds':time.monotonic()-started,'correct':any(x['document_id']==docs[i % count].pk for x in found)}
            finally:
                connections.close_all()
        start=time.monotonic()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results=list(pool.map(task,range(workers)))
        elapsed=time.monotonic()-start
        values=sorted(r['seconds'] for r in results)
        report={'kind':'synthetic_database_capacity_only','accounts':users,'documents':count,'passages':count*5,
            'concurrent_queries':workers,'correct_queries':sum(r['correct'] for r in results),
            'build_seconds':round(build_seconds,3),'query_wall_seconds':round(elapsed,3),
            'query_p50_seconds':round(values[len(values)//2],3),'query_p95_seconds':round(values[min(len(values)-1,int(len(values)*.95))],3),
            'live_research_tested':False,'notice':'合成文字资料和直接检索函数负载，不代表50人真实联网调研达标，也不代表实际企业文件分布。'}
        self.stdout.write(json.dumps(report,ensure_ascii=False,indent=2))
