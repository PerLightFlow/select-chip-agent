import tempfile
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from core.models import ResearchJob, OfficialSource, DocumentVersion, Chip, Fact, Project
from core.official_http import Snapshot, FetchError
from core.research import enqueue, process_research_once, schedule_due_sources, validate_proposals, adopt_proposals, discover, model_names
from core.knowledge import build_index, publish_version, search_documents
from core.providers import ProviderUnavailable

URL='https://docs.espressif.com/fixture.html'
HTML=b'<html><title>TEST fixture</title><main><h1>ESP32-P4</h1><p>ESP32-P4 fixture GPIO count is 8. Fictional data for automated tests only.</p></main></html>'
QUOTE='ESP32-P4 fixture GPIO count is 8.'
PROPOSAL={'chip':'ESP32-P4','key':'gpio_count','value':8,'unit':'','conditions':'','quote':QUOTE,'locator':'正文'}


@override_settings(OFFICIAL_ONLINE_ENABLED=True,ALLOW_KEYWORD_ONLY=True,
    LLM_BASE_URL='',LLM_API_KEY='',LLM_MODEL='',EMBEDDING_BASE_URL='',EMBEDDING_API_KEY='',EMBEDDING_MODEL='')
class ResearchTests(TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.override=override_settings(MEDIA_ROOT=self.tmp.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.user=get_user_model().objects.create_user('staff',password='fixture-password',is_staff=True)
        self.other=get_user_model().objects.create_user('other',password='fixture-password')
        self.client=APIClient()
        self.client.force_authenticate(self.user)

    def run_import(self,body=HTML):
        # Use a new job to explicitly test independent checks; API deduplicates recent requests.
        job=ResearchJob.objects.create(owner=self.user,kind='import',url=URL,chip='ESP32-P4')
        with patch('core.research.OfficialFetcher') as fetcher, \
             patch('core.research.propose_facts',return_value=([PROPOSAL],'fixture proposal')):
            fetcher.return_value.fetch.return_value=Snapshot(URL,body,'text/html')
            self.assertTrue(process_research_once())
        job.refresh_from_db()
        self.assertEqual(job.state,'done',job.error)
        return job,DocumentVersion.objects.get(pk=job.result['items'][0]['version_id'])

    def publish(self,v):
        v.state='indexing'
        v.save()
        build_index(v.pk)
        v.refresh_from_db()
        self.assertEqual(v.state,'ready',v.error)
        publish_version(v.pk,self.user)
        v.refresh_from_db()

    def test_import_stores_raw_snapshot_but_not_active_evidence_or_facts(self):
        job,v=self.run_import()
        self.assertTrue(v.source_digest)
        self.assertEqual(v.file.read(),HTML)
        self.assertIsNone(v.document.active_version_id)
        self.assertEqual(v.proposed_facts,[PROPOSAL])
        self.assertEqual(Fact.objects.count(),0)
        self.assertEqual(search_documents('GPIO')['items'],[])
        self.assertEqual(job.result['items'][0]['change'],'new')

    def test_duplicate_content_reuses_version(self):
        _,v=self.run_import()
        job,again=self.run_import()
        self.assertEqual(v.pk,again.pk)
        self.assertEqual(DocumentVersion.objects.count(),1)
        self.assertEqual(job.result['items'][0]['change'],'unchanged')

    def test_changed_content_keeps_published_version_until_review(self):
        _,v=self.run_import()
        self.publish(v)
        job,new=self.run_import(HTML.replace(b'count is 8',b'count is 9'))
        self.assertNotEqual(new.pk,v.pk)
        self.assertEqual(new.document.active_version_id,v.pk)
        self.assertEqual(job.result['items'][0]['change'],'changed')
        self.assertEqual({x['version_id'] for x in search_documents('GPIO')['items']},{v.pk})

    def test_version_without_embedding_stays_draft(self):
        with override_settings(ALLOW_KEYWORD_ONLY=False):
            job,v=self.run_import()
        self.assertEqual(v.state,'draft')
        self.assertIn('向量',job.result['items'][0]['notice'])

    def test_bad_html_table_keeps_raw_and_reports_manual_review(self):
        _,v=self.run_import(b'<table><tr><td colspan="2">ESP32-P4 fixture</td></tr></table>')
        self.assertEqual(v.state,'draft')
        self.assertIn('人工',v.extraction_notice)
        self.assertTrue(v.file)

    def test_fact_proposal_requires_exact_quote_model_and_locator(self):
        pages=[('正文','ESP32-P4\n'+QUOTE)]
        self.assertEqual(validate_proposals({'facts':[PROPOSAL]},pages,'ESP32-P4'),[PROPOSAL])
        for patch_values in [{'quote':'made up quotation'},{'locator':'第 5 页'},{'chip':'RK3588'},
                             {'value':float('nan')},{'unit':'x'*41},{'chip':''}]:
            self.assertEqual(validate_proposals({'facts':[{**PROPOSAL,**patch_values}]},pages,'ESP32-P4'),[])
        self.assertEqual(validate_proposals({'facts':[PROPOSAL,PROPOSAL]},pages),[])

    def test_sdk_and_similar_models_do_not_prove_compatibility(self):
        self.assertEqual(model_names('RK3588S and ESP32-P4NRW16X'),['RK3588S','ESP32-P4NRW16X'])
        self.assertEqual(validate_proposals({'facts':[{**PROPOSAL,'chip':'ESP32-P4'}]},
            [('正文','ESP32-P4NRW16X\n'+QUOTE.replace('ESP32-P4','ESP32-P4NRW16X'))]),[])

    def test_missing_model_service_retains_document(self):
        job=enqueue(self.user,kind='import',url=URL,chip='ESP32-P4')
        with patch('core.research.OfficialFetcher') as fetcher:
            fetcher.return_value.fetch.return_value=Snapshot(URL,HTML,'text/html')
            process_research_once()
        job.refresh_from_db()
        self.assertEqual(job.state,'done')
        self.assertEqual(job.result['items'][0]['proposed_facts'],[])
        self.assertIn('未生成',job.result['items'][0]['notice'])

    def test_accept_proposals_requires_publication_and_never_overwrites_conflict(self):
        _,v=self.run_import()
        chip=Chip.objects.create(model='ESP32-P4',manufacturer='fixture')
        with self.assertRaises(ValueError):
            adopt_proposals(v.pk,self.user)
        self.publish(v)
        Fact.objects.create(chip=chip,key='gpio_count',value=99,unit='',conditions='')
        result=adopt_proposals(v.pk,self.user)
        self.assertEqual(len(result['conflicts']),1)
        self.assertEqual(Fact.objects.get(chip=chip,key='gpio_count').value,99)
        Fact.objects.all().delete()
        result=adopt_proposals(v.pk,self.user)
        self.assertEqual(len(result['accepted']),1)
        self.assertTrue(Fact.objects.get().confirmed)
        self.assertEqual(Fact.objects.get().evidence.version_id,v.pk)
        self.assertEqual(adopt_proposals(v.pk,self.user)['accepted'],[])

    def test_job_ownership_and_import_role(self):
        response=self.client.post('/api/official/jobs/',{'kind':'import','url':URL},format='json')
        self.assertEqual(response.status_code,202)
        job_id=response.data['id']
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f'/api/official/jobs/{job_id}/').status_code,404)
        self.assertEqual(self.client.post('/api/official/jobs/',{'kind':'import','url':URL},format='json').status_code,403)
        self.assertEqual(self.client.post('/api/official/jobs/',{'query':'ESP32-P4'},format='json').status_code,202)

    def test_snapshot_access_is_tied_to_own_job(self):
        job,v=self.run_import()
        path=f'/api/official/jobs/{job.pk}/files/{v.pk}/'
        self.assertEqual(self.client.get(path).status_code,200)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(path).status_code,404)

    def test_request_dedup_quota_and_invalid_source(self):
        first=enqueue(self.user,query='ESP32-P4')
        self.assertEqual(enqueue(self.user,query='ESP32-P4').pk,first.pk)
        enqueue(self.user,query='RK3588')
        enqueue(self.user,query='RK3568')
        with self.assertRaisesRegex(ValueError,'3 个'):
            enqueue(self.user,query='RK3576')
        self.assertEqual(self.client.post('/api/official/jobs/',{'kind':'import','url':'https://127.0.0.1/x'},format='json').status_code,400)

    def test_fetch_failures_are_visible_and_never_marked_successful(self):
        job=enqueue(self.user,kind='import',url=URL)
        with patch('core.research.OfficialFetcher') as fetcher:
            fetcher.return_value.fetch.side_effect=FetchError('fixture blocked')
            process_research_once()
        job.refresh_from_db()
        self.assertEqual(job.state,'failed')
        self.assertIn('blocked',job.error)
        self.assertEqual(DocumentVersion.objects.count(),0)

    def test_automatic_fallback_queues_only_on_missing_evidence_and_not_demo(self):
        project=Project.objects.create(owner=self.user,title='fixture',description='ESP32-P4 GPIO')
        response=self.client.post(f'/api/projects/{project.pk}/runs/',{'auto_online':True},format='json')
        self.assertEqual(response.status_code,201)
        self.assertIn('job_id',response.data['result']['online'])
        ResearchJob.objects.all().delete()
        response=self.client.post(f'/api/projects/{project.pk}/runs/',{'auto_online':True,'demo':True},format='json')
        self.assertNotIn('online',response.data['result'])
        self.assertEqual(ResearchJob.objects.count(),0)
        self.client.post('/api/search/',{'query':'ESP32-P4','auto_online':False},format='json')
        self.assertEqual(ResearchJob.objects.count(),0)
        response=self.client.post('/api/search/',{'query':'ESP32-P4','auto_online':True},format='json')
        self.assertIn('job_id',response.data['online'])

    def test_refresh_is_opt_in_and_single_queued_job(self):
        source=OfficialSource.objects.create(url=URL,refresh_hours=0,next_check_at=timezone.now()-timedelta(hours=1))
        self.assertEqual(schedule_due_sources(),0)
        source.refresh_hours=24
        source.save()
        self.assertEqual(schedule_due_sources(),1)
        self.assertEqual(schedule_due_sources(),0)
        self.assertEqual(ResearchJob.objects.count(),1)
        self.assertIsNone(ResearchJob.objects.get().owner_id)

    @override_settings(OFFICIAL_ONLINE_ENABLED=False)
    def test_admin_can_disable_network(self):
        with self.assertRaises(ValueError):
            enqueue(self.user,query='ESP32-P4')
        self.assertEqual(schedule_due_sources(),0)

    def test_discovery_follows_relevant_official_links_and_excludes_similar_chip(self):
        seed='https://www.espressif.com/en/products/socs'
        target='https://www.espressif.com/en/products/socs/esp32-p4'
        html=b'<a href="/en/products/socs/esp32-p4">ESP32-P4</a><a href="https://evil.test/x">ESP32-P4</a>'
        def fetch(url):
            if url==seed:return Snapshot(url,html,'text/html')
            if url==target:return Snapshot(url,HTML,'text/html')
            raise FetchError('fixture missing')
        with patch('core.research.REGISTRY',{'seeds':[{'vendor':'espressif','url':seed}]}):
            fake=type('Fetcher',(),{'fetch':staticmethod(fetch)})()
            results,errors,attempts=discover('ESP32-P4',fake)
        self.assertEqual(results[0][1].url,target)
        self.assertEqual(attempts,2)
        self.assertEqual(errors,[])

    def test_corrupt_pdf_keeps_downloadable_snapshot(self):
        job=enqueue(self.user,kind='import',url=URL)
        with patch('core.research.OfficialFetcher') as fetcher:
            fetcher.return_value.fetch.return_value=Snapshot(URL,b'%PDF-broken','application/pdf')
            process_research_once()
        job.refresh_from_db()
        self.assertEqual(job.state,'done')
        item=job.result['items'][0]
        self.assertIn('人工处理',item['notice'])
        self.assertEqual(item['excerpts'],[])
        version=DocumentVersion.objects.get(pk=item['version_id'])
        self.assertEqual(version.state,'draft')
        self.assertEqual(version.file.read(),b'%PDF-broken')

    def test_discovery_ignores_dynamic_shell_with_model_only_in_url(self):
        seed='https://www.espressif.com/en/products/socs'
        shell='https://documentation.espressif.com/en/documentList?s=ESP32-P4'
        def fetch(url):
            if url==seed:
                return Snapshot(url,('<a href="'+shell+'">ESP32-P4 documentation</a>').encode(),'text/html')
            return Snapshot(url,b'<html><title>Document portal</title><main>Please enable JavaScript to load the technical documentation list.</main></html>','text/html')
        with patch('core.research.REGISTRY',{'seeds':[{'vendor':'espressif','url':seed}]}):
            fake=type('Fetcher',(),{'fetch':staticmethod(fetch)})()
            found,errors,_=discover('ESP32-P4',fake)
        self.assertEqual(found,[])
        self.assertTrue(any('动态' in e['error'] for e in errors))
