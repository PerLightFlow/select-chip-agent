from datetime import timedelta
import json
from io import StringIO
from types import SimpleNamespace
import uuid
from unittest.mock import patch

import httpx
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import transaction
from django.test import TransactionTestCase, SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from assistant.knowledge import confirm_document, withdraw_document, retrieve, index_document
from assistant.knowledge_sync import claim, step, retry
from assistant.knowledge_backends.retrieval import validate_answer_sources
from assistant.knowledge_backends.weknora import WeKnora, RemoteError, KnowledgeUnavailable
from assistant.models import KnowledgeDocument, KnowledgeVersion, KnowledgeReplica, KnowledgeCollection, EnterpriseProject, ProjectVersion


@override_settings(WEKNORA_SYNC_ENABLED=True, KNOWLEDGE_BACKEND='weknora')
class KnowledgeIntegrationTests(TransactionTestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user('owner')
        self.other = get_user_model().objects.create_user('other')
        self.collection = KnowledgeCollection.objects.create(scope='common', remote_id='kb-1')

    def document(self, title='项目设计', text='图像采集采用 ESP32-P4，张工负责电路。'):
        doc = KnowledgeDocument.objects.create(owner=self.owner, title=title)
        v = KnowledgeVersion.objects.create(document=doc, revision=1, state='indexing', text=text)
        index_document(v.pk)
        v.refresh_from_db()
        return v

    def test_management_cli_parses_and_runs_deployment_actions(self):
        output = StringIO()
        call_command('weknora_sync', 'status', stdout=output)
        self.assertIn('collections', output.getvalue())
        with patch('assistant.management.commands.weknora_sync.WeKnora') as cls:
            cls.return_value.collection.return_value = {'indexing_strategy': {
                'vector_enabled': True, 'keyword_enabled': True, 'wiki_enabled': False, 'graph_enabled': False}}
            call_command('weknora_sync', 'bind', scope='common', kb_id='kb-1', stdout=output)
        v = self.document()
        confirm_document(v.pk, self.owner)
        call_command('weknora_sync', 'backfill', stdout=output)
        call_command('weknora_sync', 'retry', version_id=v.pk, stdout=output)
        self.assertEqual(KnowledgeReplica.objects.get(version=v).state, 'queued')

    def ready(self, v, remote='remote-1'):
        confirm_document(v.pk, self.owner)
        r = KnowledgeReplica.objects.get(version=v)
        r.remote_id, r.state, r.source_ready = remote, 'ready', True
        r.save()
        return r

    def hit(self, remote='remote-1', kb='kb-1', text='张工负责电路', chunk='chunk-1'):
        return {'knowledge_id': remote, 'knowledge_base_id': kb, 'id': chunk,
                'content': text, 'source_locators': [{'type': 'pdf', 'page': 3}]}

    def test_drafts_stay_local_and_publication_is_atomic_and_idempotent(self):
        v = self.document()
        self.assertFalse(KnowledgeReplica.objects.exists())
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                confirm_document(v.pk, self.owner)
                raise RuntimeError('rollback')
        self.assertFalse(KnowledgeReplica.objects.exists())
        v.refresh_from_db()
        self.assertEqual(v.state, 'ready')
        confirm_document(v.pk, self.owner)
        confirm_document(v.pk, self.owner)
        self.assertEqual(KnowledgeReplica.objects.count(), 1)

    def test_empty_scope_never_searches_all_remote_documents(self):
        with patch('assistant.knowledge_backends.retrieval.WeKnora') as client:
            self.assertEqual(retrieve('芯片'), [])
        client.assert_not_called()

    def test_partial_backfill_returns_explicit_unavailable(self):
        v = self.document()
        confirm_document(v.pk, self.owner)
        with patch('assistant.knowledge_backends.retrieval.WeKnora') as client:
            with self.assertRaises(KnowledgeUnavailable):
                retrieve('芯片')
        client.assert_not_called()

    def test_only_approved_scope_is_sent_and_results_have_local_version_citations(self):
        v = self.document()
        self.ready(v)
        self.document('private draft')
        with patch('assistant.knowledge_backends.retrieval.WeKnora') as cls:
            cls.return_value.search.return_value = {'data': [self.hit('foreign'), self.hit(kb='wrong'), self.hit()]}
            result = retrieve('负责人')
            cls.return_value.search.assert_called_once_with('负责人', ['remote-1'])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['version_id'], v.pk)
        self.assertEqual(result[0]['title'], v.document.title)
        self.assertEqual(result[0]['locator'], '第 3 页')
        self.assertEqual(result[0]['url'], f'/api/assistant/documents/{v.document_id}/file/?version={v.pk}')

    def test_current_card_can_reference_a_shared_document_in_another_scope(self):
        v = self.document()
        self.ready(v)
        project = EnterpriseProject.objects.create(code='A', name='项目A', owner=self.owner)
        ProjectVersion.objects.create(project=project, revision=1, effective_from='2026-01-01',
                                      data={'document_ids': [v.document_id]})
        with patch('assistant.knowledge_backends.retrieval.WeKnora') as cls:
            cls.return_value.search.return_value = {'data': [self.hit()]}
            self.assertEqual(len(retrieve('负责人', project.pk)), 1)
            self.assertEqual(retrieve('负责人', project.pk + 100), [])

    def test_withdrawal_during_remote_search_filters_the_result(self):
        v = self.document()
        self.ready(v)
        def search(*args):
            withdraw_document(v.pk, self.owner)
            return {'data': [self.hit()]}
        with patch('assistant.knowledge_backends.retrieval.WeKnora') as cls:
            cls.return_value.search.side_effect = search
            self.assertEqual(retrieve('负责人'), [])

    def test_replacement_immediately_invalidates_old_version_and_answer(self):
        v = self.document()
        r = self.ready(v)
        new = KnowledgeVersion.objects.create(document=v.document, revision=2, text='新方案', state='ready')
        confirm_document(new.pk, self.owner)
        r.refresh_from_db()
        self.assertFalse(r.source_ready)
        self.assertEqual(r.state, 'queued')
        with self.assertRaises(KnowledgeUnavailable), transaction.atomic():
            validate_answer_sources([{'version_id': v.pk}])

    def remote(self, r, state='completed'):
        return {'id': 'remote-1', 'knowledge_base_id': 'kb-1', 'file_name': WeKnora.filename(r), 'parse_status': state}

    def setup_remote(self, client, r, state='completed'):
        client.collection.return_value = {'indexing_strategy': {'vector_enabled': True, 'keyword_enabled': True}}
        client.find_upload.return_value = None
        client.upload.return_value = self.remote(r, state)
        client.document.return_value = self.remote(r, state)

    def test_sync_upload_and_ready_state(self):
        v = self.document()
        confirm_document(v.pk, self.owner)
        job = claim()
        r = KnowledgeReplica.objects.get(pk=job)
        with patch('assistant.knowledge_sync.WeKnora') as cls:
            self.setup_remote(cls.return_value, r)
            step(job)
        r.refresh_from_db()
        self.assertTrue(r.source_ready)
        self.assertEqual(r.wiki_state, 'disabled')
        self.assertEqual(r.remote_id, 'remote-1')
        self.assertIsNone(claim())

    def test_lost_upload_response_is_reconciled_without_second_post(self):
        v = self.document()
        confirm_document(v.pk, self.owner)
        r = KnowledgeReplica.objects.get(pk=claim())
        with patch('assistant.knowledge_sync.WeKnora') as cls:
            self.setup_remote(cls.return_value, r)
            cls.return_value.upload.side_effect = RemoteError('timeout')
            step(r.pk)
            r.refresh_from_db()
            self.assertEqual(r.state, 'uncertain')
            retry(v.pk)
            claim()
            cls.return_value.find_upload.return_value = self.remote(r)
            step(r.pk)
            self.assertEqual(cls.return_value.upload.call_count, 1)
        r.refresh_from_db()
        self.assertTrue(r.source_ready)

    def test_uncertain_upload_with_no_remote_match_never_reposts(self):
        v = self.document()
        confirm_document(v.pk, self.owner)
        r = KnowledgeReplica.objects.get(version=v)
        r.upload_started_at = timezone.now()
        r.save()
        with patch('assistant.knowledge_sync.WeKnora') as cls:
            self.setup_remote(cls.return_value, r)
            step(claim())
            cls.return_value.upload.assert_not_called()
        r.refresh_from_db()
        self.assertEqual(r.state, 'uncertain')

    def test_withdraw_during_upload_saves_identity_then_queues_delete(self):
        v = self.document()
        confirm_document(v.pk, self.owner)
        r = KnowledgeReplica.objects.get(version=v)
        with patch('assistant.knowledge_sync.WeKnora') as cls:
            self.setup_remote(cls.return_value, r)
            def upload(*args):
                withdraw_document(v.pk, self.owner)
                return self.remote(r)
            cls.return_value.upload.side_effect = upload
            step(claim())
            r.refresh_from_db()
            self.assertFalse(r.source_ready)
            self.assertEqual(r.state, 'queued')
            step(claim())
            cls.return_value.delete.assert_called_once_with('remote-1')
            r.refresh_from_db()
            self.assertEqual(r.state, 'deleting')
            KnowledgeReplica.objects.filter(pk=r.pk).update(next_attempt_at=timezone.now())
            cls.return_value.document.side_effect = RemoteError('gone', 404)
            step(claim())
        r.refresh_from_db()
        self.assertEqual(r.state, 'deleted')

    def test_delete_ack_waits_for_absence_without_repeated_submission(self):
        v = self.document()
        r = self.ready(v)
        withdraw_document(v.pk, self.owner)
        with patch('assistant.knowledge_sync.WeKnora') as cls:
            cls.return_value.document.return_value = self.remote(r)
            step(claim())
            r.refresh_from_db()
            self.assertEqual(r.state, 'deleting')
            self.assertFalse(r.source_ready)
            KnowledgeReplica.objects.filter(pk=r.pk).update(next_attempt_at=timezone.now())
            step(claim())
            cls.return_value.delete.assert_called_once_with('remote-1')
            r.refresh_from_db()
            self.assertEqual(r.state, 'deleting')
            KnowledgeReplica.objects.filter(pk=r.pk).update(next_attempt_at=timezone.now())
            cls.return_value.document.side_effect = RemoteError('gone', 404)
            step(claim())
        r.refresh_from_db()
        self.assertEqual(r.state, 'deleted')

    def test_delete_failure_is_delayed_and_does_not_reenable_retrieval(self):
        v = self.document()
        r = self.ready(v)
        withdraw_document(v.pk, self.owner)
        with patch('assistant.knowledge_sync.WeKnora') as cls:
            cls.return_value.delete.side_effect = RemoteError('unavailable', 503)
            step(claim())
        r.refresh_from_db()
        self.assertFalse(r.source_ready)
        self.assertEqual(r.state, 'retry')
        self.assertIsNone(claim())

    def test_expired_worker_lease_is_recovered(self):
        v = self.document()
        confirm_document(v.pk, self.owner)
        job = claim()
        self.assertIsNone(claim())
        KnowledgeReplica.objects.filter(pk=job).update(next_attempt_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(claim(), job)

    def test_successful_polling_does_not_consume_network_failure_budget(self):
        v = self.document()
        r = self.ready(v)
        r.state, r.attempts, r.source_ready = 'polling', 50, False
        r.save()
        with patch('assistant.knowledge_sync.WeKnora') as cls:
            cls.return_value.document.side_effect = RemoteError('temporary', 503)
            step(claim())
        r.refresh_from_db()
        self.assertEqual(r.state, 'retry')
        self.assertEqual(r.failures, 1)

    def test_explicit_retry_reparses_failed_remote_document_without_upload(self):
        v = self.document()
        r = self.ready(v)
        r.state, r.source_ready, r.error = 'blocked', False, '原文索引失败，请管理员在知识服务检查后重试'
        r.save()
        retry(v.pk)
        with patch('assistant.knowledge_sync.WeKnora') as cls:
            step(claim())
            cls.return_value.reparse.assert_called_once_with('remote-1')
            cls.return_value.upload.assert_not_called()
        r.refresh_from_db()
        self.assertEqual(r.state, 'polling')
        self.assertFalse(r.reparse_requested)

    def test_cleanup_with_uncertain_upload_does_not_forget_possible_remote_copy(self):
        v = self.document()
        confirm_document(v.pk, self.owner)
        r = KnowledgeReplica.objects.get(version=v)
        r.upload_started_at = timezone.now()
        r.save()
        withdraw_document(v.pk, self.owner)
        with patch('assistant.knowledge_sync.WeKnora') as cls:
            cls.return_value.find_upload.return_value = None
            step(claim())
            cls.return_value.delete.assert_not_called()
        r.refresh_from_db()
        self.assertEqual(r.state, 'uncertain')
        self.assertFalse(r.source_ready)

    def test_wiki_enabled_kb_is_rejected_before_upload(self):
        v = self.document()
        confirm_document(v.pk, self.owner)
        with patch('assistant.knowledge_sync.WeKnora') as cls:
            cls.return_value.collection.return_value = {'indexing_strategy': {'wiki_enabled': True}}
            step(claim())
            cls.return_value.upload.assert_not_called()
        self.assertEqual(KnowledgeReplica.objects.get(version=v).state, 'blocked')

    def test_shared_readers_cannot_retry_others_documents(self):
        v = self.document()
        self.ready(v)
        client = APIClient()
        client.force_authenticate(self.other)
        response = client.post(f'/api/assistant/documents/{v.document_id}/', {'action': 'retry_sync', 'version_id': v.pk})
        self.assertEqual(response.status_code, 403)
        response = client.get(f'/api/assistant/documents/{v.document_id}/')
        self.assertTrue(response.data['versions'][0]['sync']['source_ready'])
        self.assertNotIn('remote_id', str(response.data))

    @override_settings(KNOWLEDGE_BACKEND='shadow')
    def test_shadow_failure_keeps_current_legacy_results(self):
        v = self.document()
        self.ready(v)
        with patch('assistant.knowledge_backends.retrieval.WeKnora') as cls:
            cls.side_effect = KnowledgeUnavailable('offline')
            self.assertEqual(retrieve('ESP32-P4')[0]['version_id'], v.pk)


@override_settings(WEKNORA_BASE_URL='http://weknora:8080', WEKNORA_READ_KEY='read-only-fixture')
class WeKnoraContractTests(SimpleTestCase):
    def test_upload_explicitly_disables_generation_despite_kb_default(self):
        replica = SimpleNamespace(pk=uuid.uuid4(), collection=SimpleNamespace(remote_id='kb-1'),
                                  version=SimpleNamespace(file=None, text='synthetic original text'))
        with patch('assistant.knowledge_backends.weknora.httpx.Client') as cls:
            client = cls.return_value.__enter__.return_value
            client.request.return_value = httpx.Response(200, json={'success': True, 'data': {'id': 'doc-1'}})
            WeKnora().upload(replica)
            kwargs = client.request.call_args.kwargs
            config = json.loads(kwargs['data']['process_config'])
            self.assertFalse(config['question_generation_config']['enabled'])
            self.assertFalse(config['summary_enabled'])
            self.assertFalse(config['graph_enabled'])
            self.assertEqual(kwargs['files']['file'][1], b'synthetic original text')

    def test_wire_scope_excludes_whole_kb_and_disables_rerank(self):
        with patch('assistant.knowledge_backends.weknora.httpx.Client') as cls:
            client = cls.return_value.__enter__.return_value
            client.request.return_value = httpx.Response(200, json={'success': True, 'data': []})
            WeKnora().search('test', ['approved'])
            kwargs = client.request.call_args.kwargs
            self.assertEqual(kwargs['json']['knowledge_ids'], ['approved'])
            self.assertNotIn('knowledge_base_ids', kwargs['json'])
            self.assertEqual(kwargs['json']['rerank'], {'enabled': False})
            self.assertEqual(kwargs['headers']['X-API-Key'], 'read-only-fixture')

    def test_errors_do_not_expose_provider_body_or_key(self):
        with patch('assistant.knowledge_backends.weknora.httpx.Client') as cls:
            client = cls.return_value.__enter__.return_value
            client.request.return_value = httpx.Response(403, text='secret-provider-response')
            with self.assertRaises(RemoteError) as error:
                WeKnora().search('test', ['approved'])
            self.assertNotIn('secret', str(error.exception))
            self.assertNotIn('fixture', str(error.exception))
            self.assertEqual(error.exception.status, 403)
