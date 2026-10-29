import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=160, default='新对话')
    brief = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=16)
    content = models.TextField()
    sources = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)


class Turn(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='turns')
    state = models.CharField(max_length=16, default='queued', db_index=True)
    events = models.JSONField(default=list)
    error = models.CharField(max_length=300, blank=True)
    usage = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['conversation'], condition=Q(state__in=['queued', 'running']), name='one_active_turn')]


class EnterpriseProject(models.Model):
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    aliases = models.JSONField(default=list)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)


class ProjectVersion(models.Model):
    project = models.ForeignKey(EnterpriseProject, on_delete=models.CASCADE, related_name='versions')
    revision = models.PositiveIntegerField()
    effective_from = models.DateField()
    data = models.JSONField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['project', 'revision'], name='unique_enterprise_revision')]
        indexes = [models.Index(fields=['project', '-effective_from', '-revision'])]


class Proposal(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    conversation = models.ForeignKey(Conversation, null=True, on_delete=models.CASCADE, related_name='proposals')
    project = models.ForeignKey(EnterpriseProject, null=True, on_delete=models.PROTECT)
    base_revision = models.PositiveIntegerField(default=0)
    data = models.JSONField()
    state = models.CharField(max_length=20, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True)


class KnowledgeDocument(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    project = models.ForeignKey(EnterpriseProject, null=True, blank=True, on_delete=models.SET_NULL)
    title = models.CharField(max_length=250)
    source_url = models.URLField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class KnowledgeVersion(models.Model):
    document = models.ForeignKey(KnowledgeDocument, on_delete=models.CASCADE, related_name='versions')
    revision = models.PositiveIntegerField()
    file = models.FileField(upload_to='enterprise/%Y/%m/', blank=True)
    text = models.TextField(blank=True)
    digest = models.CharField(max_length=64, blank=True)
    state = models.CharField(max_length=16, default='queued', db_index=True)
    error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['document', 'revision'], name='unique_knowledge_revision'),
                       models.UniqueConstraint(fields=['document'], condition=Q(state='published'), name='one_published_knowledge')]


class Passage(models.Model):
    version = models.ForeignKey(KnowledgeVersion, on_delete=models.CASCADE, related_name='passages')
    text = models.TextField()
    locator = models.CharField(max_length=200)
    search_vector = SearchVectorField(null=True)

    class Meta:
        indexes = [GinIndex(fields=['search_vector'])]
