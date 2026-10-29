#!/usr/bin/env python3
##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Run the SQLite test suite against every tracked SQLite build.

Needs the builds from ``sqlite_tracked.py`` and a Python whose ``_sqlite3``
links libsqlite3 dynamically, so ``LD_LIBRARY_PATH`` selects the version per
run. Managed interpreters (for example uv's CPython) embed SQLite and cannot
do this: a version whose interpreter does not report exactly that version is
reported as not run, never as passed. Native helpers are offered to a run
only when they were built for that version.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ElementTree

from sqlite_tracked import REPOSITORY, TRACKED, manifest, version_key


def _observed_version(python, environment):
    result = subprocess.run(
        [python, '-c', 'import sqlite3; print(sqlite3.sqlite_version)'],
        env=environment, capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def _counts(junit):
    counts = {'passed': 0, 'failed': 0, 'skipped': 0}
    for case in ElementTree.parse(junit).getroot().iter('testcase'):
        if case.find('failure') is not None or case.find('error') is not None:
            counts['failed'] += 1
        elif case.find('skipped') is not None:
            counts['skipped'] += 1
        else:
            counts['passed'] += 1
    return counts


def run_matrix(python, versions, tests, output):
    data = manifest()
    output.mkdir(parents=True, exist_ok=True)
    summary = {}
    for version in sorted(versions or data['versions'], key=version_key):
        prefix = TRACKED / version
        environment = {
            **os.environ,
            'LD_LIBRARY_PATH': str(prefix / 'lib'),
            'PYTHONPATH': os.pathsep.join(
                str(REPOSITORY / part) for part in ('tools', 'web', '.')),
            'CDEADMIN_SQLITE_HEADERS': str(prefix / 'include'),
            'CDEADMIN_SQLITE_BINARY': str(prefix / 'bin/sqlite3'),
        }
        build = prefix / 'BUILD.json'
        if not build.is_file():
            summary[version] = {'state': 'not_run',
                                'reason': 'tracked build missing'}
            continue
        helpers = json.loads(build.read_text())['helpers']
        for component, library in helpers.items():
            environment[data['helpers'][component]['environment']] = library
        observed = _observed_version(python, environment)
        if observed != version:
            summary[version] = {
                'state': 'not_run',
                'reason': f'interpreter reports SQLite {observed}; it must '
                          'link libsqlite3 dynamically'}
            continue
        junit = output / f'junit-{version}.xml'
        result = subprocess.run(
            [python, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
             f'--junitxml={junit}', *tests],
            cwd=REPOSITORY, env=environment, check=False,
            capture_output=True, text=True)
        (output / f'pytest-{version}.log').write_text(
            result.stdout + result.stderr, encoding='utf-8')
        summary[version] = {
            'state': 'run', 'helpers': sorted(helpers),
            **(_counts(junit) if junit.is_file() else {'error': 'no junit'})}
    (output / 'matrix.json').write_text(
        json.dumps(summary, indent=2, sort_keys=True) + '\n',
        encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', required=True,
                        help='interpreter with a dynamically linked _sqlite3')
    parser.add_argument('--version', action='append', dest='versions')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('tests', nargs='*',
                        default=sorted(str(path) for path in (
                            REPOSITORY / 'tools/tests').glob(
                                'test_sqlite_*.py')))
    options = parser.parse_args()
    summary = run_matrix(options.python, options.versions, options.tests,
                         options.output)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
