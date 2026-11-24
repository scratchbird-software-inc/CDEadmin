##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Regression tests for About build metadata and official brand assets."""

import json
import tempfile
from pathlib import Path
from unittest import mock

from pgadmin.about import _format_utc_and_local, _resolve_build_metadata


ROOT = Path(__file__).resolve().parents[2]


def test_brand_svg_catalog_matches_website_brand_sources():
    brand_src = ROOT / 'website' / 'assets' / 'brand'
    catalog_brand = ROOT / 'web' / 'pgadmin' / 'static' / 'assets' / 'cdeadmin' / 'branding'
    runtime_assets = ROOT / 'runtime' / 'assets'

    for name in (
        'scratchrobin.svg',
        'scratchrobin-dark.svg',
        'scratchbird.svg',
        'scratchbird-dark.svg',
        'scratchweaver.svg',
        'scratchweaver-dark.svg',
        'ddn.svg',
        'ddn-dark.svg',
        'opensource.svg',
        'opensource-dark.svg',
    ):
        assert (catalog_brand / name).read_bytes() == (brand_src / name).read_bytes()

    assert (runtime_assets / 'scratchrobin.svg').read_bytes() == (
        brand_src / 'scratchrobin.svg'
    ).read_bytes()
    assert (runtime_assets / 'scratchrobin-dark.svg').read_bytes() == (
        brand_src / 'scratchrobin-dark.svg'
    ).read_bytes()
    assert (runtime_assets / 'cdeadmin-welcome.svg').read_bytes() == (
        brand_src / 'scratchrobin-dark.svg'
    ).read_bytes()


def test_resolve_build_metadata_reads_web_and_desktop_build_info():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        web_dir = tmp_path / 'web'
        web_dir.mkdir(parents=True)
        (web_dir / 'build_info.json').write_text(
            json.dumps({
                'release': '0.325-alpha',
                'commit_hash': '1111111111111111111111111111111111111111',
                'built_at_utc': '2026-11-24T03:00:00Z',
            }),
            encoding='utf-8',
        )

        with mock.patch('pgadmin.about.config.ROOT_PATH', str(web_dir), create=True):
            meta_web = _resolve_build_metadata()
            assert meta_web['release'] == '0.325-alpha'
            assert meta_web['commit_hash'] == '1111111111111111111111111111111111111111'
            assert meta_web['build_timestamp_utc'] == '2026-11-24T03:00:00Z'
            assert '2026-11-24T03:00:00Z' in meta_web['build_datetime']

            # Desktop package BUILD_INFO.json takes precedence for packaged revision & timestamp
            (tmp_path / 'BUILD_INFO.json').write_text(
                json.dumps({
                    'source_revision': '2222222222222222222222222222222222222222',
                    'built_at_utc': '2026-11-24T04:15:30Z',
                }),
                encoding='utf-8',
            )
            meta_desktop = _resolve_build_metadata()
            assert meta_desktop['release'] == '0.325-alpha'
            assert meta_desktop['commit_hash'] == '2222222222222222222222222222222222222222'
            assert meta_desktop['build_timestamp_utc'] == '2026-11-24T04:15:30Z'
            assert meta_desktop['build_datetime'] == _format_utc_and_local('2026-11-24T04:15:30Z')
