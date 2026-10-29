import io
import copy
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from urllib.parse import urlsplit, urlunsplit
import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader
from django.conf import settings
from core.official_http import OfficialFetcher, FetchError
from .knowledge import find_projects, retrieve, propose
from .models import EnterpriseProject, ProjectVersion, Conversation

TECH_TERMS = ['MCU', 'MPU', 'SoC', 'FPGA', 'DSP', 'image sensor', 'vision AI', 'object detection',
    'image classification', 'offline inference', 'low power', 'battery', 'industrial', 'automotive',
    'Linux', 'FreeRTOS', 'bare metal', 'Cortex-M', 'Cortex-A', 'RISC-V', 'NPU', 'GPU', 'DSP acceleration',
    'MIPI CSI', 'DVP', 'MIPI DSI', 'RGB LCD', 'HDMI', 'USB', 'Ethernet', 'CAN', 'UART', 'SPI', 'I2C',
    'Wi-Fi', 'Bluetooth LE', 'SDRAM', 'PSRAM', 'DDR', 'eMMC', 'SD card', 'audio', 'motor control']


def function(name, description, properties, required):
    return {'type': 'function', 'function': {'name': name, 'description': description,
        'parameters': {'type': 'object', 'properties': properties, 'required': required, 'additionalProperties': False}}}


TOOLS = [
    function('remember_requirements', '更新本会话私有的需求摘要，用于后续多轮对话。只记录用户已说明或确认的条件、明确的修正和待澄清项；不得推测。不会保存到共享知识库。',
        {'brief': {'type': 'string', 'maxLength': 6000}}, ['brief']),
    function('search_chips', '使用公开技术条件搜索芯片。禁止发送项目名、人员名、内部原文。terms 只选提供的技术词。', {
        'terms': {'type': 'array', 'items': {'type': 'string', 'enum': TECH_TERMS}, 'maxItems': 8},
        'model': {'type': 'string', 'description': '已知的公开芯片型号，可为空'}}, ['terms', 'model']),
    function('research_chips', '优先使用：批量查询 1–5 个公开候选芯片，自动搜索并读取每个候选的来源原文，返回可对比证据和缺口。只传公开型号与技术词，不能传内部项目或人员。', {
        'models': {'type':'array','items':{'type':'string'},'minItems':1,'maxItems':5},
        'terms': {'type':'array','items':{'type':'string','enum':TECH_TERMS},'maxItems':8}}, ['models','terms']),
    function('read_source', '按本轮搜索返回的 source_id 编号读取来源原文；不要改写或猜测 URL。', {'source_id': {'type': 'integer', 'minimum':1}}, ['source_id']),
    function('query_projects', '查询企业项目卡片。query 填项目名称、代号或别名；as_of 留空查询当前，历史填 YYYY-MM-DD。',
        {'query': {'type': 'string'}, 'as_of': {'type': 'string'}}, ['query', 'as_of']),
    function('search_knowledge', '检索共享企业文档，返回原文和出处；project_id=0 表示所有项目。',
        {'query': {'type': 'string'}, 'project_id': {'type': 'integer'}}, ['query', 'project_id']),
    function('propose_project', '仅在用户要求保存或修改知识后提出项目卡片建议，不直接共享。生成的建议必须等待界面确认。data 为 JSON 字符串，字段 code,name,aliases,summary,modules,document_ids,evidence_note,effective_from。modules 中每项 name,chips,responsible,participants,notes，人员为 name,department,work。project_id=0 新建，修改时 base_revision 必须来自查询结果。',
        {'project_id': {'type': 'integer'}, 'base_revision': {'type': 'integer'}, 'data': {'type': 'string'}}, ['project_id', 'base_revision', 'data'])
]


def public_url(value, robots=False):
    if not isinstance(value, str) or len(value) > 1000 or re.search(r'[\x00-\x20\x7f\\]', value):
        raise FetchError('来源链接格式错误')
    try:
        p = urlsplit(value)
        if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None, 443):
            raise ValueError()
    except ValueError:
        raise FetchError('仅允许公开 HTTPS 来源')
    return urlunsplit(('https', p.netloc, p.path or '/', p.query, ''))


def public_query(terms, model=''):
    aliases = {t.casefold():t for t in TECH_TERMS}
    aliases.update({'mipi csi-2':'MIPI CSI', 'mipi dsi-2':'MIPI DSI', 'rtos':'FreeRTOS',
                    'camera':'image sensor', 'ai':'vision AI', '摄像头':'image sensor', '低功耗':'low power'})
    if not isinstance(terms, list) or len(terms) > 8 or any(not isinstance(t, str) or t.casefold() not in aliases for t in terms):
        raise ValueError('搜索仅接受预定义公开技术条件')
    terms = [aliases[t.casefold()] for t in terms]
    if not isinstance(model, str) or (model and not re.fullmatch(r'[A-Za-z][A-Za-z0-9._+-]{1,59}', model)):
        raise ValueError('请提供公开芯片型号，不要提供项目名称或内部原文')
    if model:
        if EnterpriseProject.objects.filter(code__iexact=model).exists() or EnterpriseProject.objects.filter(name__iexact=model).exists() or EnterpriseProject.objects.filter(aliases__contains=[model]).exists():
            raise ValueError('内部项目标识不能发往公网搜索')
        # People and departments may be Latin identifiers too.
        for data in ProjectVersion.objects.values_list('data', flat=True).iterator(chunk_size=500):
            for module in data.get('modules', []):
                for person in module.get('responsible', []) + module.get('participants', []):
                    if model.casefold() in {person.get('name', '').casefold(), person.get('department', '').casefold()}:
                        raise ValueError('内部人员标识不能发往公网搜索')
    if not terms and not model:
        raise ValueError('搜索需要技术条件或芯片型号')
    return ' '.join([*terms, model, 'semiconductor datasheet official']).strip()


def search_chips(terms, model=''):
    return _search_query(public_query(terms, model))


def _search_query(query):
    try:
        with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
            params = {'q': query, 'format': 'json', 'language': 'auto'}
            if settings.AGENT_SEARCH_ENGINES:
                params['engines'] = settings.AGENT_SEARCH_ENGINES
            response = client.get(settings.AGENT_SEARCH_URL + '/search', params=params)
            response.raise_for_status()
            data = response.json()
        results = []
        for result in data.get('results', [])[:20]:
            try:
                url = public_url(result['url'])
            except (ValueError, KeyError):
                continue
            results.append({'url': url, 'title': str(result.get('title', ''))[:250],
                'text': str(result.get('content', ''))[:800], 'kind': 'search_excerpt'})
            if len(results) >= 8:
                break
        return {'query': query, 'items': results, 'notice': '搜索摘要尚未核实；读取原文后再引用具体参数。' if results else '搜索没有返回可用来源，不能编造参数。'}
    except (httpx.HTTPError, ValueError, TypeError):
        raise ValueError('联网搜索暂时不可用，请检查搜索容器与上游服务')


# Only public technical queries and public source excerpts enter this cache.
# Shared bounded I/O avoids sending the same query 50 times during concurrent research.
_research_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix='public-research')
_research_lock = threading.Lock()
_research_cache = {}
_research_pending = {}
OFFICIAL_HOSTS = ('espressif.com', 'st.com', 'rock-chips.com', 'nxp.com', 'ti.com',
                 'microchip.com', 'renesas.com', 'nordicsemi.com', 'infineon.com',
                 'qualcomm.com', 'nvidia.com', 'ambiq.com', 'raspberrypi.com', 'analog.com')


def _research_query(model):
    # Exact candidate search avoids broad phrases that may drop the model token.
    query = f'"{model}" datasheet'
    with _research_lock:
        cached = _research_cache.get(query)
        if cached and time.monotonic() - cached[0] < (600 if cached[1]['evidence'] else 20):
            return copy.deepcopy(cached[1])
        future = _research_pending.get(query)
        owner = future is None
        if owner:
            future = _research_pending[query] = Future()
    if not owner:
        return copy.deepcopy(future.result(timeout=90))
    try:
        result = _search_query(query)
        result['evidence'], result['warnings'] = [], []
        compact = lambda value: re.sub(r'[^a-z0-9]', '', value.casefold())
        candidate = compact(model)
        # Search engines can return unrelated results with HTTP 200. Require the
        # candidate in title or URL before reading; a generic family datasheet
        # (for example ESP32) cannot serve as evidence for ESP32-P4.
        result['items'] = [item for item in result['items']
                           if candidate in compact(item['title']) or candidate in compact(item['url'])]
        if not result['items']:
            result['warnings'].append('搜索未返回与该型号匹配的来源，不能据此核实参数。')
        def priority(item):
            host = urlsplit(item['url']).hostname or ''
            official = any(host == d or host.endswith('.'+d) for d in OFFICIAL_HOSTS)
            datasheet = 'datasheet' in (item['url']+' '+item['title']).lower()
            return (official, datasheet)
        for item in sorted(result['items'], key=priority, reverse=True)[:2]:
            try:
                evidence = read_source(item['url'])
                evidence['title'] = item['title']
                evidence['text'] = evidence['text'][:9000]
                evidence['notice'] += ' 返回的是有长度限制的摘录，未覆盖内容不能据此断言。'
                if len(evidence['text'].strip()) < 150:
                    raise ValueError('来源没有足够的可读正文')
                result['evidence'].append(evidence)
                break
            except (ValueError, OSError) as exc:
                result['warnings'].append(str(exc)[:180])
        with _research_lock:
            if len(_research_cache) >= 128:
                _research_cache.pop(next(iter(_research_cache)))
            _research_cache[query] = (time.monotonic(), copy.deepcopy(result))
        future.set_result(result)
        return copy.deepcopy(result)
    except Exception as exc:
        future.set_exception(exc)
        raise
    finally:
        with _research_lock:
            _research_pending.pop(query, None)


def read_source(url):
    snapshot = OfficialFetcher(seconds=25, max_bytes=5 * 1024 * 1024, validate_url=public_url).fetch(url)
    if snapshot.content_type == 'application/pdf':
        reader = PdfReader(io.BytesIO(snapshot.body))
        if reader.is_encrypted or len(reader.pages) > 500:
            raise ValueError('PDF 过大或加密，请使用官方产品页')
        text = '\n'.join(f'第 {i+1} 页\n{p.extract_text() or ""}' for i, p in enumerate(reader.pages[:20]))
        notice = '已读取前 20 页以内；未读取的内容不能据此断言。'
    else:
        soup = BeautifulSoup(snapshot.body, 'html.parser')
        for el in soup(['script', 'style', 'nav', 'footer', 'form']):
            el.decompose()
        text, notice = soup.get_text(' ', strip=True), ''
    return {'url': snapshot.url, 'text': text[:18000], 'notice': notice, 'kind': 'source_text'}


def execute(name, args, turn, sources):
    import json
    if name == 'remember_requirements':
        brief = args.get('brief')
        if not isinstance(brief, str) or len(brief) > 6000:
            raise ValueError('需求摘要最多 6000 字符')
        Conversation.objects.filter(pk=turn.conversation_id).update(brief=brief)
        return {'notice': '本会话需求摘要已更新，仍为私有内容。'}
    if name == 'search_chips':
        result = search_chips(args.get('terms'), args.get('model', ''))
        for i, item in enumerate(result['items'], len(sources)+1):
            item['source_id'] = i
        sources.extend(result['items'])
        return result
    if name == 'research_chips':
        models = args.get('models')
        if not isinstance(models, list) or not 1 <= len(models) <= 5:
            raise ValueError('一次比较 1–5 个公开芯片型号')
        # Validate private-data boundaries on the caller's DB connection before any I/O.
        for model in models:
            public_query(args.get('terms'), model)
        # A candidate's datasheet is the same across users' application conditions.
        # Use one canonical public query per model, then compare against requirements.
        futures = [_research_pool.submit(_research_query, model) for model in models]
        deadline = time.monotonic() + 80
        results = []
        for model, future in zip(models, futures):
            try:
                result = future.result(timeout=max(0.001, deadline-time.monotonic()))
                for evidence in result['evidence']:
                    evidence['text'] = evidence['text'][:16000 // len(models)]
                for item in result['items'] + result['evidence']:
                    item['source_id'] = len(sources)+1
                    sources.append(item)
                results.append({'model':model, 'evidence':result['evidence'], 'warnings':result['warnings'],
                                'sources':[{k:x[k] for k in ['source_id','url','title']} for x in result['items'][:3]]})
            except Exception:
                future.cancel()
                results.append({'model':model,'evidence':[],'warnings':['本次公开资料查询未完成，请明确标为未核实。']})
        return {'candidates':results,'notice':'优先依据已读取原文输出对比。没有正文的候选只说明待核实条件，不要反复扩展搜索；资料不足时也先交付当前结果。'}
    if name == 'read_source':
        source_id = args.get('source_id')
        if not isinstance(source_id, int) or isinstance(source_id, bool) or not 1 <= source_id <= len(sources):
            raise ValueError('请选择本轮搜索结果中的 source_id 编号')
        source = sources[source_id-1]
        if source.get('kind') not in ['search_excerpt', 'source_text']:
            raise ValueError('只能读取本轮公开来源')
        url = source['url']
        result = read_source(url)
        result['source_id'] = len(sources)+1
        sources.append(result)
        return result
    if name == 'query_projects':
        records = find_projects(str(args.get('query', '')), args.get('as_of') or None)
        sources.extend({'url': r['url'], 'title': r['name'], 'kind': 'project_record'} for r in records)
        return {'projects': records}
    if name == 'search_knowledge':
        result = retrieve(str(args.get('query', '')), args.get('project_id') or None)
        sources.extend(result)
        return {'items': result}
    if name == 'propose_project':
        proposal = propose(turn.conversation.owner, json.loads(args['data']), args.get('project_id') or None,
                           args.get('base_revision', 0), turn.conversation)
        return {'proposal_id': proposal.pk, 'notice': '建议已生成，尚未写入共享知识，等待用户在界面确认。'}
    raise ValueError('不支持的工具')
