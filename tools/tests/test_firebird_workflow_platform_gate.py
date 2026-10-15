"""A native crash must not skip later independent workflow evidence."""
import json
from pathlib import Path
import subprocess
from tools import cdeadmin_firebird_workflow_platform_gate as gate


def test_native_crash_keeps_complete_workflow_failure_inventory(tmp_path, monkeypatch):
    source = {'sha256': 'a'*64}
    monkeypatch.setattr(gate, 'source_snapshot', lambda: source)
    called = []
    def child(args, **kwargs):
        name = args[args.index('--case')+1]
        called.append(name)
        if name == 'events':
            raise subprocess.CalledProcessError(-11, args)
        target = Path(args[args.index('--evidence')+1]);target.mkdir()
        (target/'summary.json').write_text(json.dumps({'source': source, 'source_unchanged': True,
            'checks': [{'check':name, 'status':'passed', 'proof':{'passed':True},
                        'owned_databases_removed':True, 'handles_released':True}]}))
    monkeypatch.setattr('tools.development.native.command', child)
    result = gate.run({'attachment_mode':'embedded'}, str(tmp_path), tmp_path/'evidence')
    assert called == list(gate.WORKFLOWS)
    assert not result['complete']
    assert next(x for x in result['checks'] if x['check']=='events')['status'] == 'failed'
    assert result['checks'][-1]['check']=='registration' and result['checks'][-1]['status']=='passed'
