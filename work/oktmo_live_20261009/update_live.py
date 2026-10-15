from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from system_core.core.jobs import execute_operation
from system_core.core.manifest import Operation
from system_core.core.paths import get_project_paths


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


backup_root = (WORK / 'backup').resolve()
backup_root.mkdir(parents=True, exist_ok=True)
old_rosstat_files = sorted((ROOT / 'data/rosstat').glob('*'))
backups = []
for path in old_rosstat_files:
    if not path.is_file():
        continue
    target = (backup_root / path.relative_to(ROOT)).resolve()
    if not target.is_relative_to(backup_root):
        raise RuntimeError('Backup path escaped task workspace')
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and digest(target) != digest(path):
        raise RuntimeError(f'Refusing to overwrite an earlier backup: {path.name}')
    shutil.copy2(path, target)
    assert digest(target) == digest(path)
    backups.append({'original': str(path), 'backup': str(target), 'sha256': digest(target)})
protected = []
for folder in ['input', 'output', 'config', 'data', 'system_core']:
    for path in sorted((ROOT / folder).rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts or path.name.startswith('~$') or (ROOT / 'data/rosstat') in path.parents:
            continue
        protected.append({'path': str(path), 'sha256': digest(path)})
(WORK / 'before_update.json').write_text(json.dumps({'backup': backups, 'protected': protected}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'backup_files': len(backups), 'protected_files': len(protected)}, ensure_ascii=False), flush=True)
operation = Operation(
    'update_rosstat_oktmo',
    'Update Rosstat OKTMO',
    'Download current snapshot and rebuild address lookup cache',
    'system_core.services.address_aligner_service:update_rosstat_oktmo_data',
    parameters={},
)
result = execute_operation(get_project_paths(ROOT), operation, log_callback=lambda message: print(message, flush=True))
record = {'ok': result.ok, 'message': result.message, 'data': result.data}
(WORK / 'live_update_result.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
changed = [p['path'] for p in protected if not Path(p['path']).exists() or digest(Path(p['path'])) != p['sha256']]
csv_path = Path(str(result.data.get('output_path') or ''))
csv_sha = digest(csv_path) if result.ok and csv_path.is_file() else ''
expected_sha = '2e3f1d24ebfcbcf050a1a706a77e7e9639a686749194bf5c6a8200ba598cf37a'
verification = {'protected_files_checked': len(protected), 'changed': changed, 'download_sha256': csv_sha, 'matches_fully_validated_auditor_download': csv_sha == expected_sha}
(WORK / 'verification.json').write_text(json.dumps(verification, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'ok': result.ok, 'message': result.message, 'latest_data_file': result.data.get('latest_data_file'), 'cache': result.data.get('cache'), **verification}, ensure_ascii=False), flush=True)
raise SystemExit(0 if result.ok and not changed and csv_sha == expected_sha else 1)
