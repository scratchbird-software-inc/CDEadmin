"""Bounded engine-independent DDN source conversion; never executes native SQL."""
from . import ddn_source as ddn
import json
import os
from pathlib import Path
import subprocess
import threading

_SLOTS = threading.BoundedSemaphore(2)
_RUNNER = Path(__file__).parent / 'ddn/merge_design_runner.mjs'


def merge_design(request):
    if not isinstance(request, dict) or set(request) != {'baseline', 'draft', 'incoming'}:
        raise ValueError('Original, authored and incoming DDN workspaces are required')
    try:
        for value in request.values():
            ddn.validate_workspace(value)
        encoded = json.dumps(request, ensure_ascii=False)
    except (UnicodeError, TypeError, RecursionError) as error:
        raise ValueError('Invalid DDN source encoding') from error
    if not _SLOTS.acquire(timeout=1):
        raise ValueError('Design conversion is busy; retry shortly')
    try:
        result = subprocess.run(['node', ddn.NODE_HEAP_OPTION, str(_RUNNER)],
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
        ddn.validate_workspace(snapshot)
        return snapshot
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as error:
        raise ValueError('Design conversion unavailable; the authored draft is unchanged') from error
    finally:
        _SLOTS.release()
