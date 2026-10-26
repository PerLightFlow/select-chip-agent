import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('core', '0001_initial'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name='documentversion', name='proposed_facts', field=models.JSONField(default=list, blank=True)),
        migrations.AddField(model_name='documentversion', name='extraction_notice', field=models.CharField(max_length=500, blank=True)),
        migrations.AddField(model_name='documentversion', name='fetched_at', field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name='documentversion', name='source_digest', field=models.CharField(max_length=64, blank=True)),
        migrations.CreateModel(name='OfficialSource', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('url', models.URLField(max_length=1500, unique=True)),
            ('last_digest', models.CharField(max_length=64, blank=True)),
            ('last_checked_at', models.DateTimeField(null=True, blank=True)),
            ('last_error', models.CharField(max_length=300, blank=True)),
            ('refresh_hours', models.PositiveIntegerField(default=0)),
            ('next_check_at', models.DateTimeField(null=True, blank=True)),
            ('document', models.OneToOneField(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, related_name='official_source', to='core.document')),
        ]),
        migrations.CreateModel(name='ResearchJob', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('kind', models.CharField(max_length=20, choices=[('search', '官方资料查询'), ('import', '官网链接导入')])),
            ('query', models.CharField(max_length=500, blank=True)),
            ('url', models.URLField(max_length=1500, blank=True)),
            ('chip', models.CharField(max_length=120, blank=True)),
            ('sdk', models.CharField(max_length=100, blank=True)),
            ('state', models.CharField(max_length=20, default='queued', choices=[(s, s) for s in ['queued', 'running', 'done', 'failed']])),
            ('result', models.JSONField(default=dict, blank=True)),
            ('error', models.CharField(max_length=300, blank=True)),
            ('lease', models.UUIDField(default=uuid.uuid4, editable=False)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('owner', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
        ], options={'indexes': [models.Index(fields=['state', 'created_at'], name='research_queue_idx')]}),
    ]
