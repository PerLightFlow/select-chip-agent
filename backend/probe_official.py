"""Optional live discovery diagnostics; external availability is not a CI assertion."""
import json
import os
from pathlib import Path
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from core.official_http import OfficialFetcher, FetchError
from core.research import discover

results = []
for query in ['ESP32-P4', 'RK3588']:
    try:
        found, errors, attempts = discover(query, OfficialFetcher(seconds=60))
        results.append({'query':query,'status':'ok' if found else 'unavailable','attempts':attempts,
            'items':[{'url':snapshot.url,'title':title,'content_type':snapshot.content_type,
                      'bytes':len(snapshot.body),'score':score} for score,snapshot,title in found],
            'errors':errors})
    except FetchError as exc:
        results.append({'query':query,'status':'unavailable','error':str(exc)})
output=json.dumps(results,ensure_ascii=False,indent=2)
Path('official-source-probe.json').write_text(output)
print(output)
