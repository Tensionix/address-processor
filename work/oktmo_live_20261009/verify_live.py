from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from system_core.address_engine import oktmo_lookup as lookup

result = json.loads((WORK / 'live_update_result.json').read_text(encoding='utf-8'))
assert result['ok'], result['message']
source = Path(result['data']['output_path'])
cache_path = ROOT / 'data/rosstat/oktmo_lookup_cache.json'
payload = json.loads(cache_path.read_text(encoding='utf-8'))
assert payload['source'] == lookup._csv_source_signature(source)
assert payload['cache_version'] == lookup.OKTMO_LOOKUP_CACHE_VERSION
assert len(payload['index']) == result['data']['cache']['index_keys']
assert len(payload['context_by_code']) == result['data']['cache']['contexts']
with source.open('rb') as handle:
    assert hashlib.file_digest(handle, 'sha256').hexdigest() == '2e3f1d24ebfcbcf050a1a706a77e7e9639a686749194bf5c6a8200ba598cf37a'
del payload

# Require loading from the newly created disk cache, rather than silently
# rebuilding an index in this independent verification process.
def unexpected_rebuild(*args, **kwargs):
    raise AssertionError('The saved index was not accepted in a fresh process')
lookup._build_index = unexpected_rebuild
status = lookup.warm_oktmo_cache(ROOT / 'data')
assert status['regions'] == 89 and status['cache_exists']
with source.open(encoding='utf-8-sig', newline='') as handle:
    localities = [r for r in csv.reader(handle, delimiter=';') if r[:3] == ['05', '540', '000'] and r[5] == '2' and r[3] != '000']
verified = []
for row in localities:
    code = ''.join(row[:4])
    name = row[6].strip()
    context = lookup.oktmo_context_by_code(ROOT / 'data', code)
    assert context is not None and context.oktmo_code == code
    matched = lookup.lookup_oktmo(name, ROOT / 'data', subject_hint='Приморский край', subject_ter_hint='05', municipality_hint='Тернейский муниципальный округ')
    assert matched is not None and matched[0] == code, (name, code, matched)
    verified.append({'name': name, 'code': code})
assert len(verified) == 11
report = {'saved_cache_accepted_in_fresh_process': True, 'cache_source_matches_csv': True, 'source_sha256_matches_auditor': True, 'cache': status, 'terney_localities_found': verified}
(WORK / 'live_verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
