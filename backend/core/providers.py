import hashlib
import json
import math
import httpx
from django.conf import settings


class ProviderUnavailable(Exception):
    pass


def embedding_profile():
    if not all([settings.EMBEDDING_BASE_URL, settings.EMBEDDING_API_KEY, settings.EMBEDDING_MODEL]):
        return ''
    value = [settings.EMBEDDING_BASE_URL, settings.EMBEDDING_MODEL,
        settings.EMBEDDING_REVISION, settings.EMBEDDING_DIMENSIONS, 'paragraph-v1']
    return hashlib.sha256(json.dumps(value).encode()).hexdigest()


def embed(texts):
    if not embedding_profile():
        raise ProviderUnavailable('未配置 Embedding 服务')
    result = []
    try:
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            for offset in range(0, len(texts), 16):
                batch = texts[offset:offset + 16]
                response = client.post(settings.EMBEDDING_BASE_URL + '/embeddings',
                    headers={'Authorization': 'Bearer ' + settings.EMBEDDING_API_KEY},
                    json={'model': settings.EMBEDDING_MODEL, 'input': batch})
                response.raise_for_status()
                data = sorted(response.json()['data'], key=lambda x: x['index'])
                if [x['index'] for x in data] != list(range(len(batch))):
                    raise ValueError('Embedding 索引不完整')
                for item in data:
                    vector = item['embedding']
                    if not isinstance(vector, list) or len(vector) != settings.EMBEDDING_DIMENSIONS:
                        raise ValueError('Embedding 维度不匹配')
                    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in vector):
                        raise ValueError('Embedding 数值无效')
                    if not any(v != 0 for v in vector):
                        raise ValueError('Embedding 不能为零向量')
                    result.append(vector)
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise ProviderUnavailable('Embedding 调用失败或返回格式不匹配') from exc
    return result


def chat_json(system, user):
    if not all([settings.LLM_BASE_URL, settings.LLM_API_KEY, settings.LLM_MODEL]):
        raise ProviderUnavailable('未配置对话模型，使用表单及规则流程')
    try:
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            response = client.post(settings.LLM_BASE_URL + '/chat/completions',
                headers={'Authorization': 'Bearer ' + settings.LLM_API_KEY},
                json={'model': settings.LLM_MODEL, 'temperature': 0,
                    'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
                    'response_format': {'type': 'json_object'}, 'max_tokens': 1600})
            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content']
            result = json.loads(content)
            if not isinstance(result, dict):
                raise ValueError('Expected object')
            return result
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise ProviderUnavailable('对话模型调用失败，保留规则结果') from exc
