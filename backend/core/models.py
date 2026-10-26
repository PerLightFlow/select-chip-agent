import uuid
from django.conf import settings
from django.db import models
from pgvector.django import VectorField


class Document(models.Model):
    title = models.CharField(max_length=250)
    source_url = models.URLField(blank=True, max_length=1000)
    is_demo = models.BooleanField(default=False)
    active_version = models.ForeignKey('DocumentVersion', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class DocumentVersion(models.Model):
    STATES = [(s, s) for s in ['draft', 'queued', 'indexing', 'ready', 'published', 'withdrawn', 'failed']]
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name='versions')
    revision = models.CharField(max_length=100)
    text = models.TextField(blank=True)
    file = models.FileField(upload_to='documents/%Y/%m/', blank=True)
    chip_models = models.JSONField(default=list, blank=True, help_text='适用型号数组；空数组表示未核实')
    sdk_version = models.CharField(max_length=100, blank=True)
    task = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=20, choices=STATES, default='draft')
    digest = models.CharField(max_length=64, blank=True)
    embedding_profile = models.CharField(max_length=200, blank=True)
    index_generation = models.UUIDField(default=uuid.uuid4, editable=False)
    proposed_facts = models.JSONField(default=list, blank=True)
    extraction_notice = models.CharField(max_length=500, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)
    source_digest = models.CharField(max_length=64, blank=True)
    error = models.CharField(max_length=250, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['document', 'revision'], name='unique_doc_revision')]

    def __str__(self):
        return f'{self.document} / {self.revision} ({self.state})'


class Chunk(models.Model):
    version = models.ForeignKey(DocumentVersion, on_delete=models.CASCADE, related_name='chunks')
    ordinal = models.PositiveIntegerField()
    text = models.TextField()
    locator = models.CharField(max_length=200)
    terms = models.TextField()
    embedding = VectorField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['version', 'ordinal'], name='unique_chunk_ordinal')]


class Chip(models.Model):
    manufacturer = models.CharField(max_length=100)
    family = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=120, unique=True)
    sku = models.CharField(max_length=160, blank=True)
    role = models.CharField(max_length=80, default='主控')
    lifecycle = models.CharField(max_length=30, choices=[(s, s) for s in ['unknown','production','nrnd','eol','sample']], default='unknown')
    sale_status = models.CharField(max_length=30, choices=[(s, s) for s in ['unknown','verified','unavailable']], default='unknown')
    aliases = models.JSONField(default=list, blank=True)
    is_demo = models.BooleanField(default=False)
    published = models.BooleanField(default=False)
    revision = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.model


class Fact(models.Model):
    chip = models.ForeignKey(Chip, on_delete=models.CASCADE, related_name='facts')
    key = models.CharField(max_length=100)
    value = models.JSONField(help_text='数字、字符串、布尔值或数组')
    unit = models.CharField(max_length=40, blank=True)
    conditions = models.CharField(max_length=500, blank=True)
    evidence = models.ForeignKey(Chunk, null=True, blank=True, on_delete=models.PROTECT)
    confirmed = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['chip','key'], name='unique_chip_fact')]


class Algorithm(models.Model):
    name = models.CharField(max_length=200)
    task = models.CharField(max_length=100)
    chip = models.ForeignKey(Chip, on_delete=models.CASCADE, related_name='algorithms')
    model_variant = models.CharField(max_length=150, blank=True)
    sdk_version = models.CharField(max_length=100)
    precision = models.CharField(max_length=30, blank=True)
    conditions = models.JSONField(default=dict, blank=True)
    benchmark = models.JSONField(default=dict, blank=True, help_text='须注明输入、批量、频率与测量范围')
    evidence = models.ForeignKey(Chunk, on_delete=models.PROTECT)
    published = models.BooleanField(default=False)

    def __str__(self):
        return f'{self.chip} / {self.name}'


class Project(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    requirements = models.JSONField(default=list, blank=True)
    task = models.CharField(max_length=100, blank=True)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class SelectionRun(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='runs')
    snapshot = models.JSONField()
    result = models.JSONField()
    rules_version = models.CharField(max_length=60, default='0.1.0')
    created_at = models.DateTimeField(auto_now_add=True)


class SearchRun(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    query = models.TextField()
    filters = models.JSONField(default=dict)
    result = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=80)
    target = models.CharField(max_length=160)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class OfficialSource(models.Model):
    url = models.URLField(max_length=1500, unique=True)
    document = models.OneToOneField(Document, null=True, blank=True, on_delete=models.PROTECT, related_name='official_source')
    last_digest = models.CharField(max_length=64, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True)
    # 0 disables polling; admins opt in per source.
    refresh_hours = models.PositiveIntegerField(default=0)
    next_check_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.url


class ResearchJob(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    kind = models.CharField(max_length=20, choices=[('search', '官方资料查询'), ('import', '官网链接导入')])
    query = models.CharField(max_length=500, blank=True)
    url = models.URLField(max_length=1500, blank=True)
    chip = models.CharField(max_length=120, blank=True)
    sdk = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=20, default='queued',
        choices=[(s, s) for s in ['queued', 'running', 'done', 'failed']])
    result = models.JSONField(default=dict, blank=True)
    error = models.CharField(max_length=300, blank=True)
    lease = models.UUIDField(default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['state', 'created_at'], name='research_queue_idx')]
