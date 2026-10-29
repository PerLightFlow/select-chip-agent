import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import pgvector.django

D = django.db.models.deletion

def pk():
    return ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID'))

class Migration(migrations.Migration):
    initial=True
    dependencies=[migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[
        pgvector.django.VectorExtension(),
        migrations.CreateModel(name='Document',fields=[pk(),
            ('title',models.CharField(max_length=250)),('source_url',models.URLField(blank=True,max_length=1000)),
            ('is_demo',models.BooleanField(default=False)),('created_at',models.DateTimeField(auto_now_add=True))]),
        migrations.CreateModel(name='DocumentVersion',fields=[pk(),
            ('revision',models.CharField(max_length=100)),('text',models.TextField(blank=True)),
            ('file',models.FileField(blank=True,upload_to='documents/%Y/%m/')),
            ('chip_models',models.JSONField(blank=True,default=list,help_text='适用型号数组；空数组表示未核实')),
            ('sdk_version',models.CharField(blank=True,max_length=100)),('task',models.CharField(blank=True,max_length=100)),
            ('state',models.CharField(choices=[(s,s) for s in ['draft','queued','indexing','ready','published','withdrawn','failed']],default='draft',max_length=20)),
            ('digest',models.CharField(blank=True,max_length=64)),('embedding_profile',models.CharField(blank=True,max_length=200)),
            ('index_generation',models.UUIDField(default=uuid.uuid4,editable=False)),('error',models.CharField(blank=True,max_length=250)),
            ('attempts',models.PositiveIntegerField(default=0)),('updated_at',models.DateTimeField(auto_now=True)),
            ('published_at',models.DateTimeField(blank=True,null=True)),
            ('document',models.ForeignKey(on_delete=D.PROTECT,related_name='versions',to='core.document')),
            ('reviewed_by',models.ForeignKey(blank=True,null=True,on_delete=D.SET_NULL,to=settings.AUTH_USER_MODEL))],
            options={'constraints':[models.UniqueConstraint(fields=('document','revision'),name='unique_doc_revision')]}),
        migrations.AddField(model_name='document',name='active_version',field=models.ForeignKey(blank=True,null=True,on_delete=D.SET_NULL,related_name='+',to='core.documentversion')),
        migrations.CreateModel(name='Chunk',fields=[pk(),('ordinal',models.PositiveIntegerField()),('text',models.TextField()),
            ('locator',models.CharField(max_length=200)),('terms',models.TextField()),('embedding',pgvector.django.VectorField(blank=True,null=True)),
            ('version',models.ForeignKey(on_delete=D.CASCADE,related_name='chunks',to='core.documentversion'))],
            options={'constraints':[models.UniqueConstraint(fields=('version','ordinal'),name='unique_chunk_ordinal')]}),
        migrations.CreateModel(name='Chip',fields=[pk(),('manufacturer',models.CharField(max_length=100)),
            ('family',models.CharField(blank=True,max_length=100)),('model',models.CharField(max_length=120,unique=True)),
            ('sku',models.CharField(blank=True,max_length=160)),('role',models.CharField(default='主控',max_length=80)),
            ('lifecycle',models.CharField(choices=[(s,s) for s in ['unknown','production','nrnd','eol','sample']],default='unknown',max_length=30)),
            ('sale_status',models.CharField(choices=[(s,s) for s in ['unknown','verified','unavailable']],default='unknown',max_length=30)),
            ('aliases',models.JSONField(blank=True,default=list)),('is_demo',models.BooleanField(default=False)),
            ('published',models.BooleanField(default=False)),('revision',models.PositiveIntegerField(default=1)),('updated_at',models.DateTimeField(auto_now=True))]),
        migrations.CreateModel(name='Fact',fields=[pk(),('key',models.CharField(max_length=100)),
            ('value',models.JSONField(help_text='数字、字符串、布尔值或数组')),('unit',models.CharField(blank=True,max_length=40)),
            ('conditions',models.CharField(blank=True,max_length=500)),('confirmed',models.BooleanField(default=False)),
            ('chip',models.ForeignKey(on_delete=D.CASCADE,related_name='facts',to='core.chip')),
            ('evidence',models.ForeignKey(blank=True,null=True,on_delete=D.PROTECT,to='core.chunk'))],
            options={'constraints':[models.UniqueConstraint(fields=('chip','key'),name='unique_chip_fact')]}),
        migrations.CreateModel(name='Algorithm',fields=[pk(),('name',models.CharField(max_length=200)),
            ('task',models.CharField(max_length=100)),('model_variant',models.CharField(blank=True,max_length=150)),
            ('sdk_version',models.CharField(max_length=100)),('precision',models.CharField(blank=True,max_length=30)),
            ('conditions',models.JSONField(blank=True,default=dict)),('benchmark',models.JSONField(blank=True,default=dict,help_text='须注明输入、批量、频率与测量范围')),
            ('published',models.BooleanField(default=False)),('chip',models.ForeignKey(on_delete=D.CASCADE,related_name='algorithms',to='core.chip')),
            ('evidence',models.ForeignKey(on_delete=D.PROTECT,to='core.chunk'))]),
        migrations.CreateModel(name='Project',fields=[pk(),('title',models.CharField(max_length=200)),
            ('description',models.TextField(blank=True)),('requirements',models.JSONField(blank=True,default=list)),
            ('task',models.CharField(blank=True,max_length=100)),('revision',models.PositiveIntegerField(default=1)),
            ('created_at',models.DateTimeField(auto_now_add=True)),('updated_at',models.DateTimeField(auto_now=True)),
            ('owner',models.ForeignKey(on_delete=D.CASCADE,to=settings.AUTH_USER_MODEL))]),
        migrations.CreateModel(name='SelectionRun',fields=[pk(),('snapshot',models.JSONField()),('result',models.JSONField()),
            ('rules_version',models.CharField(default='0.1.0',max_length=60)),('created_at',models.DateTimeField(auto_now_add=True)),
            ('project',models.ForeignKey(on_delete=D.CASCADE,related_name='runs',to='core.project'))]),
        migrations.CreateModel(name='SearchRun',fields=[pk(),('query',models.TextField()),('filters',models.JSONField(default=dict)),
            ('result',models.JSONField()),('created_at',models.DateTimeField(auto_now_add=True)),
            ('owner',models.ForeignKey(on_delete=D.CASCADE,to=settings.AUTH_USER_MODEL))]),
        migrations.CreateModel(name='AuditEvent',fields=[pk(),('action',models.CharField(max_length=80)),
            ('target',models.CharField(max_length=160)),('detail',models.JSONField(default=dict)),('created_at',models.DateTimeField(auto_now_add=True)),
            ('actor',models.ForeignKey(null=True,on_delete=D.SET_NULL,to=settings.AUTH_USER_MODEL))]),
    ]
