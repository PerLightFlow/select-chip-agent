from django.contrib import admin, messages
from .models import Document, DocumentVersion, Chunk, Chip, Fact, Algorithm, AuditEvent, Project, SelectionRun, SearchRun
from .knowledge import queue_index, publish_version, withdraw_version
from .models import OfficialSource, ResearchJob
from .research import adopt_proposals, enqueue
from .official_http import official_url
from django.utils import timezone
from django import forms


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'is_demo', 'active_version']
    readonly_fields = ['active_version', 'created_at']
    search_fields = ['title']

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields + (['is_demo'] if obj and obj.versions.exists() else [])


@admin.register(DocumentVersion)
class VersionAdmin(admin.ModelAdmin):
    list_display = ['document', 'revision', 'state', 'attempts', 'updated_at']
    list_filter = ['state', 'document__is_demo']
    readonly_fields = ['state','digest','embedding_profile','index_generation','error','attempts','updated_at','reviewed_by','published_at','proposed_facts','extraction_notice','fetched_at','source_digest']
    actions = ['queue', 'publish', 'withdraw', 'adopt']

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.state not in {'draft','failed'}:
            editable = {'chip_models','sdk_version','task'} if obj.state == 'ready' else set()
            return [f.name for f in self.model._meta.fields if f.name not in editable]
        return self.readonly_fields

    def has_delete_permission(self, request, obj=None):
        return False

    def perform(self, request, queryset, fn):
        for obj in queryset:
            try:
                fn(obj.pk, request.user)
                self.message_user(request, f'{obj.revision} 操作完成')
            except ValueError as exc:
                self.message_user(request, str(exc), messages.ERROR)

    @admin.action(description='生成待审核索引')
    def queue(self, request, queryset):
        self.perform(request, queryset, queue_index)

    @admin.action(description='审核通过并发布所选版本')
    def publish(self, request, queryset):
        self.perform(request, queryset, publish_version)

    @admin.action(description='已逐项核验：采纳无冲突参数建议（须先发布文档）')
    def adopt(self, request, queryset):
        for obj in queryset:
            try:
                result = adopt_proposals(obj.pk, request.user)
                self.message_user(request, f"新增 {len(result['accepted'])} 项；冲突 {len(result['conflicts'])} 项；跳过 {len(result['skipped'])} 项。详细差异见审计记录。")
            except ValueError as exc:
                self.message_user(request, str(exc), messages.ERROR)

    @admin.action(description='撤回所选版本')
    def withdraw(self, request, queryset):
        self.perform(request, queryset, withdraw_version)


class FactInline(admin.TabularInline):
    model = Fact
    extra = 0


@admin.register(Chip)
class ChipAdmin(admin.ModelAdmin):
    list_display = ['model','manufacturer','sale_status','lifecycle','published','is_demo']
    list_filter = ['manufacturer','published','is_demo']
    search_fields = ['model','manufacturer']
    inlines = [FactInline]
    readonly_fields = ['revision','updated_at']

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields + (['is_demo'] if obj else [])

    def save_model(self, request, obj, form, change):
        if change:
            obj.revision += 1
        super().save_model(request, obj, form, change)
        AuditEvent.objects.create(actor=request.user, action='edit_chip', target=str(obj.pk), detail={'revision':obj.revision})


@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
    list_display = ['id','version','locator']
    search_fields = ['text','version__document__title']
    readonly_fields = [f.name for f in Chunk._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditEvent, SelectionRun, SearchRun)
class HistoryAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

admin.site.register(Algorithm)
admin.site.register(Project)
admin.site.site_header = 'Select Chip · 公共知识库管理'


class SourceForm(forms.ModelForm):
    class Meta:
        model = OfficialSource
        fields = '__all__'

    def clean_url(self):
        try:
            return official_url(self.cleaned_data['url'])
        except ValueError as exc:
            raise forms.ValidationError(str(exc))

    def clean_refresh_hours(self):
        value = self.cleaned_data['refresh_hours']
        if value > 8760:
            raise forms.ValidationError('自动检查间隔为 0 至 8760 小时；0 表示关闭')
        return value


@admin.register(OfficialSource)
class SourceAdmin(admin.ModelAdmin):
    form = SourceForm
    list_display = ['url','last_checked_at','refresh_hours','next_check_at','last_error']
    readonly_fields = ['document','last_digest','last_checked_at','last_error','next_check_at']
    actions = ['refresh_now']

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields + (['url'] if obj else [])

    def save_model(self, request, obj, form, change):
        obj.next_check_at = timezone.now() if obj.refresh_hours else None
        super().save_model(request,obj,form,change)

    @admin.action(description='检查官网是否更新（不会自动发布）')
    def refresh_now(self, request, queryset):
        for source in queryset:
            try:
                job = enqueue(request.user,kind='import',url=source.url)
                self.message_user(request,f'已提交联网任务 #{job.pk}')
            except ValueError as exc:
                self.message_user(request,str(exc),messages.ERROR)


@admin.register(ResearchJob)
class ResearchJobAdmin(HistoryAdmin):
    list_display = ['id','kind','chip','state','owner','created_at']
    list_filter = ['state','kind']
    readonly_fields = [f.name for f in ResearchJob._meta.fields]
