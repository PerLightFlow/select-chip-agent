"""Optional live diagnostics; network availability is not a deterministic CI assertion."""
import json
from pathlib import Path
from core.official_http import OfficialFetcher, FetchError

results = []
for url in ['https://www.espressif.com/en/products/socs',
            'https://www.rock-chips.com/a/cn/product/index.html']:
    try:
        snapshot = OfficialFetcher(seconds=25).fetch(url)
        results.append({'url':url,'status':'ok','final_url':snapshot.url,
            'content_type':snapshot.content_type,'bytes':len(snapshot.body)})
    except FetchError as exc:
        results.append({'url':url,'status':'unavailable','error':str(exc)})
output = json.dumps(results, ensure_ascii=False, indent=2)
Path('official-source-probe.json').write_text(output)
print(output)
