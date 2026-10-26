from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core import views, research_views

router = DefaultRouter()
router.register('projects',views.ProjectViewSet,basename='project')
urlpatterns = [path('api/official/jobs/',research_views.jobs),
    path('api/official/jobs/<int:job_id>/',research_views.job_detail),
    path('api/official/jobs/<int:job_id>/files/<int:version_id>/',research_views.snapshot_file),
    path('api/official/sources/',research_views.source_list),path('admin/',admin.site.urls),path('api/',include(router.urls)),
    path('api/health/',views.health),path('api/session/',views.session),
    path('api/login/',views.sign_in),path('api/logout/',views.sign_out),
    path('api/analyze/',views.analyze),path('api/chips/',views.chips),path('api/stats/',views.stats),
    path('api/search/',views.search),path('api/evidence/<int:chunk_id>/',views.evidence),
    path('api/documents/<int:version_id>/file/',views.document_file),
    path('api/projects/<int:project_id>/runs/',views.project_runs),
    path('api/runs/<int:run_id>/export/',views.export_run)]
