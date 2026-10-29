"""Tools are not offered on runtimes that cannot serve them (owner
direction 2026-10-29: surface every feature, filter per engine)."""
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.context_menu import declared_tool_actions  # noqa
from pgadmin.cdeadmin.providers.sqlite.native_helpers import (  # noqa
    HELPER_MINIMUM,
)

TOOLS = ROOT / 'web/pgadmin/cdeadmin/ui_descriptors/sqlite/tools.json'


def _recover(scope, slot, runtime_version, **state):
    actions = declared_tool_actions(
        'sqlite', scope, slot, state={
            'engine_id': 'sqlite', 'display': 'SQLite', 'owner': True,
            'verified': True, 'database_target_id': 'target',
            'runtime_version': runtime_version, **state})
    return next(action for action in actions
                if action['label'] == 'Recover SQLite file...')


@pytest.mark.parametrize('scope,slot', [
    ('endpoint', 'after_verify'), ('database', 'pre_lifecycle')])
@pytest.mark.parametrize('runtime,enabled', [
    ('3.35.0', False), ('3.44.0', False), ('3.45.1', True),
    ('3.53.0', True), (None, True)])
def test_recovery_tool_follows_the_recovery_helper_minimum(
        scope, slot, runtime, enabled):
    action = _recover(scope, slot, runtime)
    assert action['enabled'] is enabled
    if not enabled:
        assert '3.45.1' in action['disabled_reason']


def test_tool_gate_matches_the_helper_minimum():
    """One evidence-based minimum: the tool gate must not drift from it."""
    tools = json.loads(TOOLS.read_text())['tools']
    gates = {tool['version']['minimum'] for tool in tools
             if tool.get('arguments', {}).get('tab') == 'sqlite-recovery'}
    assert gates == {HELPER_MINIMUM['recovery']}


def test_owner_condition_still_decides_first():
    action = _recover('endpoint', 'after_verify', '3.53.0', owner=False)
    assert action['enabled'] is False
    assert 'owner' in action['disabled_reason']
