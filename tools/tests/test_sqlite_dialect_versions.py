"""Versioned SQLite dialect tables (owner direction, 2026-10-29)."""
import copy
import json
import sqlite3
import sys
from pathlib import Path

import pytest

# Reuse only the established package bootstrap.
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite import dialect_versions
from pgadmin.cdeadmin.providers.sqlite.provider import PROFILE

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/reference_engine_demos'))
import merge_sqlite_dialect_versions as merge_tool  # noqa: E402

PROVIDER = ROOT / 'web/pgadmin/cdeadmin/providers/sqlite'
REFERENCE_INVENTORY = PROVIDER / 'sqlite_dialect_inventory_3_53_0.json'


@pytest.fixture(scope='module')
def table():
    return dialect_versions.versioned_table()


def test_reference_is_reproduced_exactly(table):
    committed = json.loads(REFERENCE_INVENTORY.read_text())['inventories']
    assert merge_tool.inventory_for(table, '3.53.0') == committed
    assert dialect_versions.inventory_for('3.53.0') == committed


def test_tracked_versions_start_at_the_declared_floor(table):
    tracked = table['tracked_versions']
    assert tracked == sorted(tracked, key=merge_tool.version_key)
    assert tracked[0] == PROFILE.minimum_version
    assert tracked[-1] == PROFILE.exact_version
    assert set(table['sources']) == set(tracked)


def test_keys_are_unique_and_intervals_are_ordered(table):
    tracked = table['tracked_versions']
    for name, items in table['inventories'].items():
        keys = [item['key'] for item in items]
        assert len(keys) == len(set(keys)), name
        for item in items:
            present = item['present_in']
            assert present == [v for v in tracked if v in present]
            assert item['introduced_in'] == present[0]
            if item['introduced_after'] is not None:
                assert tracked.index(item['introduced_after']) + 1 == (
                    tracked.index(item['introduced_in']))
            if item['removed_in'] is not None:
                assert tracked.index(item['removed_in']) == (
                    tracked.index(present[-1]) + 1)


# Each addition is cited from the sqlite.org release log of the version
# that introduced it; the merged interval must contain that version.
CITED_ADDITIONS = [
    ('unixepoch', '3.38.0', 'https://www.sqlite.org/releaselog/3_38_0.html'),
    ('octet_length', '3.43.0',
     'https://www.sqlite.org/releaselog/3_43_0.html'),
    ('timediff', '3.43.0', 'https://www.sqlite.org/releaselog/3_43_0.html'),
    ('concat_ws', '3.44.0', 'https://www.sqlite.org/releaselog/3_44_0.html'),
    ('jsonb', '3.45.0', 'https://www.sqlite.org/releaselog/3_45_0.html'),
    ('json_pretty', '3.46.0',
     'https://www.sqlite.org/releaselog/3_46_0.html'),
]


@pytest.mark.parametrize('name,added,citation', CITED_ADDITIONS)
def test_cited_function_additions_fall_in_their_interval(
        table, name, added, citation):
    entry = next(item for item in table['derived']['function_names']
                 if item['function_name'] == name)
    key = merge_tool.version_key
    assert entry['introduced_after'] is not None, citation
    assert key(entry['introduced_after']) < key(added), citation
    assert key(added) <= key(entry['introduced_in']), citation
    assert entry['removed_in'] is None


def test_strict_types_only_where_strict_tables_exist(table):
    strict = [item for item in table['inventories']['data_types']
              if item['record'].get('strict_table_type')]
    assert strict
    # STRICT tables are absent from 3.35.0 (runtime-probed, not assumed).
    assert all('3.35.0' not in item['present_in'] for item in strict)


def test_signature_notation_change_is_not_a_removal(table):
    names = {item['function_name']: item
             for item in table['derived']['function_names']}
    for name in ('coalesce', 'max', 'min', 'iif', 'concat', 'concat_ws'):
        assert names[name]['removed_in'] is None, name
    changed = [item for item in table['inventories']['functions']
               if item.get('signature_changed_in')]
    assert changed and all(item['signature_successors'] for item in changed)


@pytest.mark.parametrize('runtime,selected,newer', [
    ('3.35.0', '3.35.0', False),
    ('3.40.1', '3.35.0', False),
    ('3.45.1', '3.45.1', False),
    ('3.46.0', '3.45.1', False),
    ('3.53.0', '3.53.0', False),
    ('3.53.1', '3.53.0', True),
    ('3.60.0', '3.53.0', True),
])
def test_runtime_maps_to_greatest_tracked_version(runtime, selected, newer):
    assert dialect_versions.table_version_for(runtime) == (selected, newer)


def test_runtime_below_floor_has_no_table():
    with pytest.raises(ValueError, match='outside the supported'):
        dialect_versions.table_version_for('3.34.1')


def test_function_availability_follows_the_runtime_table():
    assert not dialect_versions.function_available('unixepoch', '3.35.0')
    assert dialect_versions.function_available('unixepoch', '3.45.1')
    assert not dialect_versions.function_available('json_pretty', '3.46.0')
    assert dialect_versions.function_available('json_pretty', '3.53.0')


def test_retirement_prunes_versions_and_their_only_records(table):
    retired = merge_tool.retire_below(copy.deepcopy(table), '3.45.1')
    assert retired['tracked_versions'] == ['3.45.1', '3.53.0']
    names = {item['function_name']
             for item in retired['derived']['function_names']}
    assert 'fts5_decode' not in names  # existed only in retired 3.35.0
    assert merge_tool.inventory_for(retired, '3.53.0') == (
        merge_tool.inventory_for(table, '3.53.0'))
    with pytest.raises(RuntimeError):
        merge_tool.retire_below(copy.deepcopy(table), '3.54.0')


def test_editor_seeds_keywords_from_the_running_runtime_table(
        tmp_path, monkeypatch):
    """The static keyword seed (used when the native keyword API is not
    available) comes from the running runtime's table. The native API, when
    available, still decides: e.g. WITHIN is listed in the 3.53.0 source but
    is a keyword only with SQLITE_ENABLE_ORDERED_SET_AGGREGATES."""
    import re
    from pgadmin.cdeadmin.providers import native_editor
    from pgadmin.cdeadmin.providers.sqlite import identifier_keywords
    seeded = {}

    def capture(handle, words):
        seeded['words'] = list(words)
        return {}, []

    monkeypatch.setattr(identifier_keywords, 'observe', capture)
    connection = sqlite3.connect(str(tmp_path / 'editor.sqlite'))
    try:
        native_editor.metadata(connection, 'sqlite')
    finally:
        connection.close()
    expected = [
        row['native_name'] for row in dialect_versions.inventory_for(
            sqlite3.sqlite_version)['lexical_rules']
        if re.fullmatch(r'[A-Za-z][A-Za-z0-9_$]*', row['native_name'])]
    assert seeded['words'] == expected
    selected, _newer = dialect_versions.table_version_for(
        sqlite3.sqlite_version)
    assert ('WITHIN' in seeded['words']) == (selected == '3.53.0')


def test_conditional_keywords_keep_their_compile_option_mask(table):
    within = next(item for item in table['inventories']['lexical_rules']
                  if item['key'] == 'WITHIN')
    assert within['record']['feature_mask'] == 'ORDERSET'
