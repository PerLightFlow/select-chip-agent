from unittest.mock import patch
from django.test import TestCase, override_settings, Client
from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient
from core.models import Document, DocumentVersion, Chunk, Chip, Fact, Project, SelectionRun
from core.knowledge import search_documents, queue_index, publish_version, withdraw_version, tokenize
from core.providers import embedding_profile, ProviderUnavailable


@override_settings(EMBEDDING_BASE_URL='',EMBEDDING_API_KEY='',EMBEDDING_MODEL='')
class KnowledgeTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user(username='alice',password='long-example-password')
        self.other=get_user_model().objects.create_user(username='bob',password='another-example-password')
        self.client=APIClient()
        self.client.force_authenticate(self.user)
        self.doc=Document.objects.create(title='Power guide')
        self.v=DocumentVersion.objects.create(document=self.doc,revision='1',text='低功耗休眠支持传感器唤醒。 sleep sensor wakeup',chip_models=['TestChip'])

    def publish(self):
        with override_settings(ALLOW_KEYWORD_ONLY=True):
            queue_index(self.v.pk,self.user)
            call_command('worker',once=True)
            publish_version(self.v.pk,self.user)
        self.v.refresh_from_db()

    def test_drafts_and_withdrawn_never_retrieved(self):
        self.assertEqual(search_documents('休眠')['items'],[])
        self.publish()
        self.assertEqual(len(search_documents('休眠')['items']),1)
        withdraw_version(self.v.pk,self.user)
        self.assertEqual(search_documents('休眠')['items'],[])

    def test_ready_index_requires_publication(self):
        with override_settings(ALLOW_KEYWORD_ONLY=True):
            queue_index(self.v.pk,self.user)
            call_command('worker',once=True)
        self.assertEqual(search_documents('休眠')['items'],[])

    def test_formal_semantic_build_fails_without_provider(self):
        queue_index(self.v.pk,self.user)
        call_command('worker',once=True)
        self.v.refresh_from_db()
        self.assertEqual(self.v.state,'failed')
        with self.assertRaises(ValueError):publish_version(self.v.pk,self.user)

    def test_new_version_replaces_search_and_withdrawal_does_not_revive_old(self):
        self.publish()
        v2=DocumentVersion.objects.create(document=self.doc,revision='2',text='休眠新版本，需外接传感器。',chip_models=['TestChip'])
        with override_settings(ALLOW_KEYWORD_ONLY=True):
            queue_index(v2.pk,self.user);call_command('worker',once=True);publish_version(v2.pk,self.user)
        self.assertEqual({x['version_id'] for x in search_documents('休眠')['items']},{v2.pk})
        withdraw_version(v2.pk,self.user)
        self.assertEqual(search_documents('休眠')['items'],[])

    def test_exact_model_filter_does_not_match_similar_name(self):
        self.publish()
        self.assertEqual(search_documents('休眠',chip='TestChip2')['items'],[])
        self.assertEqual(len(search_documents('休眠',chip='TestChip')['items']),1)

    def test_demo_excluded_by_default(self):
        call_command('seed_demo')
        self.assertEqual(self.client.get('/api/chips/').data['items'],[])
        self.assertEqual(len(self.client.get('/api/chips/?demo=true').data['items']),2)

    def test_shared_knowledge_and_owned_projects(self):
        self.publish()
        p=Project.objects.create(owner=self.user,title='private project')
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f'/api/projects/{p.pk}/').status_code,404)
        self.assertEqual(self.client.post(f'/api/projects/{p.pk}/runs/',{},format='json').status_code,404)
        self.assertEqual(len(self.client.post('/api/search/',{'query':'休眠'},format='json').data['items']),1)

    def test_unauthenticated_denied_and_csrf_login_protected(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/chips/').status_code,403)
        client=Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/api/login/',data={'username':'alice','password':'long-example-password'},content_type='application/json').status_code,403)
        client.get('/api/session/')
        token=client.cookies['csrftoken'].value
        self.assertEqual(client.post('/api/login/',data={'username':'alice','password':'long-example-password'},content_type='application/json',HTTP_X_CSRFTOKEN=token).status_code,200)

    def test_project_save_and_selection_snapshot(self):
        call_command('seed_demo')
        r=self.client.post('/api/projects/',{'title':'Linux product','requirements':[{'key':'os','op':'eq','value':'Linux','unit':'','hard':True}]},format='json')
        self.assertEqual(r.status_code,201)
        run=self.client.post(f"/api/projects/{r.data['id']}/runs/",{'demo':True},format='json')
        self.assertEqual(run.status_code,201)
        candidates=run.data['result']['candidates']
        self.assertEqual(candidates[0]['model'],'DEMO-SOC-B')
        self.assertEqual(candidates[-1]['status'],'fail')
        before=SelectionRun.objects.get(pk=run.data['id']).result
        Chip.objects.filter(model='DEMO-SOC-B').update(published=False)
        self.assertEqual(SelectionRun.objects.get(pk=run.data['id']).result,before)

    @override_settings(EMBEDDING_BASE_URL='https://example.invalid/v1',EMBEDDING_API_KEY='test',EMBEDDING_MODEL='fixture',EMBEDDING_DIMENSIONS=3)
    def test_real_pgvector_path_and_provider_failure_fallback(self):
        queue_index(self.v.pk,self.user)
        with patch('core.knowledge.embed',return_value=[[1.0,0.0,0.0]]):
            call_command('worker',once=True)
        publish_version(self.v.pk,self.user)
        with patch('core.knowledge.embed',return_value=[[1.0,0.0,0.0]]):
            result=search_documents('battery standby')
        self.assertEqual(result['mode'],'hybrid')
        self.assertEqual(len(result['items']),1)
        with patch('core.knowledge.embed',side_effect=ProviderUnavailable('unavailable')):
            result=search_documents('休眠')
        self.assertEqual(result['mode'],'keyword')
        self.assertIn('降级',result['notice'])
