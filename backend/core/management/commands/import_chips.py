import csv
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from openpyxl import load_workbook
from core.models import Chip, AuditEvent


class Command(BaseCommand):
    help = '预览 CSV/XLSX 型号目录；--apply 将新型号作为未发布草稿导入，不覆盖已有记录'

    def add_arguments(self,parser):
        parser.add_argument('file')
        parser.add_argument('--apply',action='store_true')

    def handle(self,*args,**options):
        path=Path(options['file'])
        if path.suffix.lower()=='.xlsx':
            wb=load_workbook(path,read_only=True,data_only=True)
            try:
                iterator=iter(wb.active.values)
                headers=next(iterator)
                rows=[dict(zip(headers,row)) for row in iterator]
            finally:
                wb.close()
        else:
            with path.open(encoding='utf-8-sig',newline='') as f:
                rows=list(csv.DictReader(f))
        seen=set()
        entries=[]
        for index,row in enumerate(rows,2):
            data={k:str(row.get(k) or '').strip() for k in ['manufacturer','family','model','sku','role']}
            if not data['model'] or not data['manufacturer'] or data['model'] in seen:
                raise CommandError(f'第 {index} 行缺少型号/厂商或批次内重复')
            if len(data['model'])>120 or len(data['manufacturer'])>100 or len(data['sku'])>160:
                raise CommandError(f'第 {index} 行字段过长')
            seen.add(data['model'])
            if not Chip.objects.filter(model=data['model']).exists():
                entries.append(data)
        self.stdout.write(f'共 {len(rows)} 行，新增 {len(entries)} 个草稿，已有型号跳过。')
        if options['apply']:
            with transaction.atomic():
                Chip.objects.bulk_create([Chip(**d) for d in entries])
                AuditEvent.objects.create(action='import_catalog',target=path.name,detail={'created':len(entries)})
            self.stdout.write('已导入；需补充证据、核验状态并在后台发布。')
