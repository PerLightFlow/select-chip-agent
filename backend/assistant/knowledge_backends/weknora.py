"""Small, bounded v0.9.0 API client. No upstream errors or credentials reach users."""
import json
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
from django.conf import settings


class KnowledgeUnavailable(ValueError):
    pass


class RemoteError(KnowledgeUnavailable):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def segment(value):
    return quote(str(value), safe='')


def upload_filename(replica):
    suffix = Path(replica.version.file.name).suffix.lower() if replica.version.file else '.md'
    return f'sca-{replica.pk.hex}{suffix}'


class WeKnora:
    def __init__(self, write=False):
        self.base = settings.WEKNORA_BASE_URL
        self.key = settings.WEKNORA_WRITE_KEY if write else settings.WEKNORA_READ_KEY
        url = urlsplit(self.base)
        if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password or url.query or url.fragment or not self.key:
            raise KnowledgeUnavailable('企业知识服务尚未配置，请联系管理员')

    def request(self, method, path, *, enveloped=True, **kwargs):
        try:
            with httpx.Client(timeout=httpx.Timeout(settings.WEKNORA_TIMEOUT, connect=5),
                              follow_redirects=False, trust_env=False) as client:
                response = client.request(method, self.base + '/api/v1' + path,
                    headers={'X-API-Key': self.key, 'Accept-Language': 'zh-CN'}, **kwargs)
            if not 200 <= response.status_code < 300:
                raise RemoteError(f'企业知识服务请求失败（HTTP {response.status_code}）', response.status_code)
            if method == 'DELETE' and response.status_code == 204:
                return {'success': True}
            if len(response.content) > 8 * 1024 * 1024:
                raise RemoteError('企业知识服务返回内容过大')
            data = response.json()
            if not isinstance(data, dict) or (enveloped and data.get('success') is not True):
                raise RemoteError('企业知识服务返回格式异常')
            return data
        except RemoteError:
            raise
        except (httpx.HTTPError, ValueError):
            raise RemoteError('企业知识服务不可用或响应超时，请稍后重试') from None

    def collection(self, kb):
        return self.request('GET', '/knowledge-bases/' + segment(kb))['data']

    def search(self, query, ids):
        # Never send a whole KB alongside IDs: upstream combines them as a union.
        if not ids:
            return {'data': []}
        return self.request('POST', '/knowledge-search', json={
            'query': query[:1000], 'knowledge_ids': ids, 'match_count': 32,
            'rerank': {'enabled': False},
        })

    def document(self, remote_id):
        return self.request('GET', '/knowledge/' + segment(remote_id))['data']

    def reparse(self, remote_id):
        self.request('POST', '/knowledge/' + segment(remote_id) + '/reparse', json={'process_config': self.process_config()})

    def spans(self, remote_id):
        return self.request('GET', '/knowledge/' + segment(remote_id) + '/spans')['data']

    def wiki_stats(self, kb):
        return self.request('GET', '/knowledgebase/' + segment(kb) + '/wiki/stats', enveloped=False)

    def wiki_pages(self, kb):
        pages = []
        for number in range(1, settings.WEKNORA_WIKI_MAX_PAGES // 100 + 2):
            data = self.request('GET', '/knowledgebase/' + segment(kb) + '/wiki/pages', enveloped=False,
                                params={'page': number, 'page_size': 100, 'sort_by': 'slug', 'sort_order': 'asc'})
            items = data.get('pages')
            if not isinstance(items, list):
                raise RemoteError('Wiki 页面列表格式异常')
            pages.extend(items)
            if len(pages) > settings.WEKNORA_WIKI_MAX_PAGES:
                raise RemoteError('Wiki 页面过多，请管理员调整处理范围')
            if len(pages) >= data.get('total', len(pages)) or not items:
                return pages
        raise RemoteError('Wiki 页面分页未完成')

    def delete(self, remote_id):
        try:
            self.request('DELETE', '/knowledge/' + segment(remote_id))
        except RemoteError as exc:
            if exc.status != 404:
                raise

    @staticmethod
    def filename(replica):
        return upload_filename(replica)

    def find_upload(self, replica):
        # The durable random filename is sent in the create request itself, so
        # response loss can be reconciled without relying on a later metadata PUT.
        marker = self.filename(replica)
        result = self.request('GET', '/knowledge-bases/' + segment(replica.collection.remote_id) + '/knowledge',
                              params={'keyword': marker, 'page': 1, 'page_size': 100})
        items = result.get('data')
        if not isinstance(items, list):
            raise RemoteError('企业知识服务文档列表格式异常')
        matches = [x for x in items if x.get('file_name') == marker]
        if len(matches) > 1 or len(items) >= 100:
            raise RemoteError('发现重复同步记录，请管理员核对后处理')
        return matches[0] if matches else None

    def upload(self, replica):
        data = {'fileName': self.filename(replica), 'channel': 'api', 'process_config': json.dumps(self.process_config())}
        path = '/knowledge-bases/' + segment(replica.collection.remote_id) + '/knowledge/file'
        v = replica.version
        if v.file:
            with v.file.open('rb') as stream:
                return self.request('POST', path, data=data,
                    files={'file': (self.filename(replica), stream, 'application/octet-stream')})['data']
        return self.request('POST', path, data=data,
            files={'file': (self.filename(replica), v.text.encode('utf-8'), 'text/markdown')})['data']

    @staticmethod
    def process_config():
        # Wiki follows the KB strategy. Keep other generation disabled on upload AND reparse.
        return {'summary_enabled': False, 'enable_multimodel': False,
                'graph_enabled': False, 'question_generation_config': {'enabled': False}}

    def label(self, replica):
        self.request('PUT', '/knowledge/' + segment(replica.remote_id), json={
            'title': replica.version.document.title,
            'custom_metadata': {'application': 'select-chip-agent',
                                'version_id': str(replica.version_id),
                                'digest': replica.version.digest},
        })
