import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from assistant.knowledge_sync import claim, step
from assistant.wiki import refresh_one


class Command(BaseCommand):
    help = '独立运行 WeKnora 资料同步；默认单并发，支持重启后恢复'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        if not settings.WEKNORA_SYNC_ENABLED:
            raise CommandError('请先配置 WEKNORA_SYNC_ENABLED=1')
        while True:
            close_old_connections()
            job = claim()
            if job:
                step(job)
            refresh_one()
            if options['once']:
                return
            if not job:
                time.sleep(2)
