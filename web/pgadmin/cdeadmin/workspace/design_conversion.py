"""Bounded engine-independent DDN source conversion; never executes native SQL."""
import json
import os
from pathlib import Path
import subprocess
import threading

_SLOTS = threading.BoundedSemaphore(2)
_RUNNER = Path(__file__).parent / 'ddn/merge_design_runner.mjs'
_MAX_BYTES = 8 * 1024 * 1024


def _snapshot(value):
    if (not isinstance(value, dict) or set(value) != {'format', 'entry', 'view', 'files'} or
            value['format'] != 'ddn-workspace@1' or not isinstance(value['files'], dict) or
            not 1 <= len(value['files']) <= 64 or not isinstance(value['entry'], str) or
            value['entry'] not in value['files'] or not isinstance(value['view'], str) or
            not value['view']):
        raise ValueError('Invalid DDN source workspace')
    for name, source in value['files'].items():
        if (not isinstance(name, str) or len(name) > 1024 or not name.endswith('.ddn') or
                any(part in {'', '.', '..'} for part in name.split('/')) or
                '\\' in name or '\0' in name or not isinstance(source, str) or
                len(source.encode('utf-16-le')) // 2 > 2000000):
            raise ValueError('Invalid DDN source file')
    if len(json.dumps(value, ensure_ascii=False).encode('utf-8')) > _MAX_BYTES:
        raise ValueError('DDN design exceeds 8 MiB')


def merge_design(request):
    if not isinstance(request, dict) or set(request) != {'baseline', 'draft', 'incoming'}:
        raise ValueError('Original, authored and incoming DDN workspaces are required')
    try:
        for value in request.values():
            _snapshot(value)
        encoded = json.dumps(request, ensure_ascii=False)
    except (UnicodeError, TypeError, RecursionError) as error:
        raise ValueError('Invalid DDN source encoding') from error
    if not _SLOTS.acquire(timeout=1):
        raise ValueError('Design conversion is busy; retry shortly')
    try:
        result = subprocess.run(['node', '--max-old-space-size=256', str(_RUNNER)],
            input=encoded, text=True, encoding='utf-8', capture_output=True, timeout=30,
            env={key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'TMPDIR') if key in os.environ})
        if result.returncode:
            # Only the runner's structured diagnostic is admitted; never return
            # native stack traces, process diagnostics or server filesystem paths.
            try:
                failure = json.loads(result.stdout)
                message = failure['error']
                if not isinstance(message, str) or len(message) > 2048:
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                message = 'Design conversion failed; the authored draft is unchanged'
            raise ValueError(message)
        snapshot = json.loads(result.stdout)
        _snapshot(snapshot)
        return snapshot
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as error:
        raise ValueError('Design conversion unavailable; the authored draft is unchanged') from error
    finally:
        _SLOTS.release()
