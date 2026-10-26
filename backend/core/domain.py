"""Deterministic selection rules. No network or framework dependencies."""
import math
import re

OPS = {'eq', 'gte', 'lte', 'contains'}


def validate_requirements(items):
    if not isinstance(items, list) or len(items) > 30:
        raise ValueError('需求必须是数组，最多 30 项')
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('每项需求必须是对象')
        key, op = item.get('key', ''), item.get('op', 'eq')
        if not isinstance(key, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,79}', key) or op not in OPS:
            raise ValueError('字段名或比较方式无效')
        value = item.get('value')
        if not isinstance(value, (str, int, float, bool)) or isinstance(value, str) and len(value) > 300:
            raise ValueError('需求值必须是有限数字、布尔值或短文本')
        if isinstance(value, (int, float)) and not isinstance(value, bool) and not math.isfinite(value):
            raise ValueError('数值必须有限')
        if op in {'gte', 'lte'} and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise ValueError('大小比较需要数字')
        if not isinstance(item.get('hard', True), bool):
            raise ValueError('hard 必须是布尔值')
        for field in ['unit', 'conditions', 'source']:
            if not isinstance(item.get(field, ''), str) or len(item.get(field, '')) > 600:
                raise ValueError(f'{field} 必须是短文本')
        result.append({'key': key, 'op': op, 'value': value, 'unit': item.get('unit', ''),
            'hard': item.get('hard', True), 'conditions': item.get('conditions', ''),
            'source': item.get('source', '')})
    return result


def evaluate(requirement, fact):
    pending = {'status': 'unknown', 'reason': '缺少已确认且有效的字段证据'}
    if not fact or not fact.get('confirmed') or not fact.get('evidence_valid'):
        return pending
    if fact.get('unit', '') != requirement.get('unit', ''):
        return {'status': 'unknown', 'reason': '单位不同，需要规范化后比较'}
    if fact.get('conditions', '') != requirement.get('conditions', ''):
        return {'status': 'unknown', 'reason': '适用条件不同或尚未确认'}
    actual, expected, op = fact['value'], requirement['value'], requirement['op']
    if op in {'gte', 'lte'}:
        if isinstance(actual, bool) or not isinstance(actual, (int, float)) or not math.isfinite(actual):
            return {'status': 'unknown', 'reason': '字段不是可比较的有限数字'}
        ok = actual >= expected if op == 'gte' else actual <= expected
    elif op == 'contains':
        if not isinstance(actual, list):
            return {'status': 'unknown', 'reason': '字段不是能力列表'}
        ok = expected in actual
    else:
        if isinstance(actual, bool) != isinstance(expected, bool):
            return {'status': 'unknown', 'reason': '字段类型不一致'}
        ok = actual == expected
    return {'status': 'pass' if ok else 'fail', 'reason': '满足该项约束' if ok else '不满足该项约束',
        'actual': actual, 'evidence_id': fact.get('evidence_id')}


def evaluate_chip(chip, requirements):
    checks = [{**r, **evaluate(r, chip.get('facts', {}).get(r['key']))} for r in requirements]
    hard = [c for c in checks if c['hard']]
    status = 'pass'
    if any(c['status'] == 'fail' for c in hard):
        status = 'fail'
    elif not hard or any(c['status'] == 'unknown' for c in hard):
        status = 'unknown'
    return {**chip, 'checks': checks, 'status': status,
        'soft_passes': sum(c['status'] == 'pass' for c in checks if not c['hard']),
        'warnings': (['NRND：新设计优先核对替代型号'] if chip.get('lifecycle') == 'nrnd' else [])
        + (['当前在售状态尚未核实'] if chip.get('sale_status') != 'verified' else [])}


def rank_candidates(chips, requirements):
    return sorted([evaluate_chip(c, requirements) for c in chips], key=lambda c: (
        {'pass': 0, 'unknown': 1, 'fail': 2}[c['status']],
        sum(x['status'] == 'unknown' for x in c['checks'] if x['hard']),
        c.get('lifecycle') != 'production', -c['soft_passes'], c['model']))


def reciprocal_rank_fusion(*rankings, k=60):
    scores = {}
    for ranking in rankings:
        for rank, item in enumerate(dict.fromkeys(ranking), 1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda x: (-scores[x], x)), scores


def split_blocks(text, max_chars=1400):
    """Keep paragraph/table blocks intact; oversize blocks remain reviewable."""
    blocks = re.split(r'\n\s*\n', text.strip())
    output, current = [], ''
    for block in blocks:
        if not block.strip():
            continue
        if current and len(current) + len(block) > max_chars:
            output.append(current)
            current = ''
        current = (current + '\n\n' + block).strip()
    if current:
        output.append(current)
    return output
