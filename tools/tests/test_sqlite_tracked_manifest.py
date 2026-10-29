"""The tracked-SQLite manifest stays consistent with the provider."""
import json
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.providers.sqlite.native_helpers import (  # noqa
    HELPER_MINIMUM,
)
from pgadmin.cdeadmin.providers.sqlite.provider import PROFILE  # noqa

MANIFEST = json.loads(
    (ROOT / 'tools/reference_engine_demos/sqlite_tracked_versions.json')
    .read_text())
TABLE = json.loads(
    (ROOT / 'web/pgadmin/cdeadmin/providers/sqlite/'
            'sqlite_dialect_versions.json').read_text())


def test_helper_minimums_match_the_provider():
    assert {name: spec['minimum']
            for name, spec in MANIFEST['helpers'].items()} == HELPER_MINIMUM


def test_tracked_versions_match_the_versioned_table():
    assert sorted(MANIFEST['versions']) == sorted(TABLE['tracked_versions'])
    assert min(MANIFEST['versions'], key=lambda v: tuple(
        int(part) for part in v.split('.'))) == PROFILE.minimum_version


def test_every_version_is_pinned_and_verified():
    for version, entry in MANIFEST['versions'].items():
        assert entry['source_archive'].startswith('https://www.sqlite.org/')
        assert len(entry['source_archive_sha256']) == 64, version
        assert len(entry['check_in']) == 64, version
        assert len(entry['sqlite3_c_sha3_256']) == 64, version
        assert 'releaselog' in entry['verified_against'], version
