from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from .domain import rank_candidates, validate_requirements
from .knowledge import evidence_valid, search_documents
from .models import Chip
from .providers import chat_json, ProviderUnavailable


class SelectionState(TypedDict, total=False):
    requirements: list
    description: str
    task: str
    demo: bool
    candidates: list
    evidence: dict
    result: dict


def parse_requirements(text):
    prompt = '''你是嵌入式产品需求分析助手。只提取用户明确给出的约束，不猜测芯片参数。
返回 JSON: {"requirements":[],"questions":[],"task":""}。questions 最多三个问题。
requirements 每项为 {key,op,value,unit,hard,source,conditions}，source 必须是用户原文片段。
key 使用 snake_case；op 为 eq/gte/lte/contains；hard 为布尔值。
常用字段: os(字符串), ram_mb(MiB), gpio_count(数量), interfaces(contains), wireless(contains)。
成本、功耗和实时性缺少口径时只提问，不生成已确定的约束。无法确认的单位只提问。
任务 task 可为 classification、detection 或空。此输出是待用户确认的建议。'''
    try:
        result = chat_json(prompt, text[:10000])
        requirements = validate_requirements(result.get('requirements', []))
        if any(not r['source'] or r['source'] not in text for r in requirements):
            raise ValueError('原文定位失败')
        questions = result.get('questions', [])
        if not isinstance(questions, list):
            raise ValueError('问题格式不正确')
        task = result.get('task', '')
        return {'requirements': requirements, 'questions': [q[:400] for q in questions if isinstance(q, str)][:3],
            'task': task if task in {'classification','detection',''} else '', 'mode': 'llm', 'notice': '请核对并保存需求后再选型'}
    except (ProviderUnavailable, ValueError, TypeError) as exc:
        return {'requirements': [], 'task': '', 'mode': 'form', 'notice': str(exc),
            'questions': ['必须支持哪些接口、操作系统和通信方式？',
                '内存、成本与功耗的硬性上限或下限是什么？', '算法任务和实时性目标是什么，是否包含前后处理？']}


def select_node(state):
    chips = []
    for chip in Chip.objects.filter(published=True, is_demo=state['demo']).prefetch_related(
            'facts__evidence__version__document', 'algorithms__evidence__version__document'):
        facts = {f.key: {'value': f.value, 'unit': f.unit, 'conditions': f.conditions,
            'confirmed': f.confirmed, 'evidence_id': f.evidence_id,
            'evidence_valid': evidence_valid(f.evidence, state['demo'], chip.model)} for f in chip.facts.all()}
        algorithms = [{'name': a.name, 'variant': a.model_variant, 'task': a.task,
            'sdk_version': a.sdk_version, 'precision': a.precision, 'conditions': a.conditions,
            'benchmark': a.benchmark, 'evidence_id': a.evidence_id} for a in chip.algorithms.all()
            if a.published and evidence_valid(a.evidence, state['demo'], chip.model, a.sdk_version) and (not state['task'] or a.task == state['task'])]
        chips.append({'id': chip.pk, 'model': chip.model, 'manufacturer': chip.manufacturer,
            'revision': chip.revision, 'sku': chip.sku, 'lifecycle': chip.lifecycle,
            'sale_status': chip.sale_status, 'facts': facts, 'algorithms': algorithms,
            'is_demo': chip.is_demo})
    return {'candidates': rank_candidates(chips, state['requirements'])}


def retrieve_node(state):
    return {'evidence': search_documents(state['description'] or state['task'], demo=state['demo'])}


def report_node(state):
    passed = [c for c in state['candidates'] if c['status'] == 'pass']
    unknown = [c for c in state['candidates'] if c['status'] == 'unknown']
    if not state['requirements']:
        summary = '请先确认硬性需求。当前结果仅供浏览，不构成已验证的选型推荐。'
    elif not passed:
        summary = '当前数据库没有已证实满足全部硬约束的候选，请核对冲突项及待验证条件。'
    else:
        summary = f'发现 {len(passed)} 个满足已录入硬约束的候选，仍需核对板级配置及实际应用条件。'
    if state['task']:
        summary += ' 算法建议依据已有资料；未上传计算图或接入实机，未验证实际实时性。'
    return {'result': {'summary': summary, 'recommended_ids': [c['id'] for c in passed[:3]],
        'pending_ids': [c['id'] for c in unknown], 'candidates': state['candidates'],
        'evidence': state['evidence'], 'is_demo': state['demo']}}


builder = StateGraph(SelectionState)
builder.add_node('select', select_node)
builder.add_node('retrieve', retrieve_node)
builder.add_node('report', report_node)
builder.add_edge(START, 'select')
builder.add_edge('select', 'retrieve')
builder.add_edge('retrieve', 'report')
builder.add_edge('report', END)
selection_graph = builder.compile()
