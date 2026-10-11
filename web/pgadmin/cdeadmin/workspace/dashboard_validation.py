"""Bounded host validation using the paired DDN runtime, never browser code."""
from functools import lru_cache
import json
import os
from pathlib import Path
import subprocess
import threading

from .assets import ProjectAssetError

_ROOT = Path(__file__).resolve().parents[2]
_RUNNER = Path(__file__).parent / 'ddn/validate_dashboard.mjs'
_INPUTS = (_RUNNER, _ROOT / 'static/vendor/ddn/current/ddn.mjs',
           _ROOT / 'static/js/cdeadmin_ui/integrations/ddn/dashboardPublication.mjs')
_SLOTS = threading.BoundedSemaphore(2)


@lru_cache(maxsize=64)
def _validate(node, payload, generation):
    if not _SLOTS.acquire(timeout=1):
        raise RuntimeError('Dashboard validator is busy')
    try:
        env = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'TMPDIR')
               if key in os.environ}
        result = subprocess.run([node, '--max-old-space-size=128', str(_RUNNER)], input=payload, text=True,
                                capture_output=True, timeout=8, env=env, check=False)
        if result.returncode:
            raise ProjectAssetError('Dashboard source or metric bindings are invalid')
        return result.stdout
    finally:
        _SLOTS.release()


def validate_dashboard(snapshot, scope, node='node'):
    files = snapshot.get('files', {}) if isinstance(snapshot, dict) else {}
    if (not isinstance(files, dict) or len(files) != 1 or
            any(not isinstance(value, str) or len(value.encode()) > 512 * 1024
                for value in files.values())):
        raise ProjectAssetError('Dashboard source exceeds its admitted limits')
    payload = json.dumps({'snapshot': snapshot, 'scope': scope}, sort_keys=True)
    if len(payload.encode()) > 2 * 1024 * 1024:
        raise ProjectAssetError('Dashboard request exceeds its admitted limits')
    generation = tuple((path.stat().st_mtime_ns, path.stat().st_size) for path in _INPUTS)
    return json.loads(_validate(node, payload, generation))
