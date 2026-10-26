from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Document, DocumentVersion, Chunk, Chip, Fact, Algorithm
from core.knowledge import tokenize


class Command(BaseCommand):
    help = '创建独立的虚构演示数据；不会创建或替代正式芯片资料'

    @transaction.atomic
    def handle(self,*args,**kwargs):
        if Chip.objects.filter(model='DEMO-MCU-A').exists():
            self.stdout.write('演示数据已存在，未覆盖')
            return
        doc = Document.objects.create(title='演示资料 · 虚构参数，仅用于验证流程',is_demo=True)
        text = 'DEMO-MCU-A 是虚构主控，使用 FreeRTOS，片上 RAM 为 2 MiB，GPIO 数量为 20。支持低功耗休眠与传感器唤醒。DEMO-SOC-B 是虚构 Linux SoC，参考配置 RAM 为 512 MiB，GPIO 为 32。全部数据为测试夹具，不能用于真实选型。'
        v = DocumentVersion.objects.create(document=doc,revision='demo-1',text=text,state='published',
            chip_models=['DEMO-MCU-A','DEMO-SOC-B'])
        doc.active_version=v
        doc.save()
        c = Chunk.objects.create(version=v,ordinal=0,text=text,terms=tokenize(text),locator='演示正文')
        for name,os_name,ram,gpio in [('DEMO-MCU-A','FreeRTOS',2,20),('DEMO-SOC-B','Linux',512,32)]:
            chip = Chip.objects.create(model=name,manufacturer='虚构厂商',is_demo=True,published=True,
                lifecycle='production',sale_status='unknown',role='主控' if ram==2 else 'SoC')
            for key,value,unit in [('os',os_name,''),('ram_mb',ram,'MiB'),('gpio_count',gpio,'')]:
                Fact.objects.create(chip=chip,key=key,value=value,unit=unit,evidence=c,confirmed=True)
        self.stdout.write('已创建 2 个虚构演示型号；正式库保持为空。')
