from django.urls import path
from . import views

urlpatterns = [
    path('conversations/', views.conversations),
    path('conversations/<uuid:conversation_id>/', views.conversation),
    path('conversations/<uuid:conversation_id>/messages/', views.send_message),
    path('turns/<uuid:turn_id>/stop/', views.stop_turn),
    path('projects/', views.projects), path('projects/<int:project_id>/', views.project_detail),
    path('proposals/', views.proposals), path('proposals/<int:proposal_id>/', views.proposal_action),
    path('documents/', views.documents), path('documents/<int:document_id>/', views.document_detail),
    path('documents/<int:document_id>/file/', views.document_file), path('search/', views.search),
    path('wiki/', views.wiki_pages), path('wiki/<uuid:page_id>/', views.wiki_page),
]
