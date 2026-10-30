#!/usr/bin/env python3
"""Render the PostgreSQL-wire parity probe results as the matrix in the docs.

Reads ``tools/reference_engine_demos/postgresql_wire_parity/*.json`` (written
by ``cdeadmin_postgresql_wire_parity_probe.py``) and replaces the table
between the ``.. parity-matrix-start`` and ``.. parity-matrix-end`` comments
in ``docs/en_US/postgresql_wire_parity.rst``. ``--check`` fails when the
committed table differs from the results instead of writing it.
"""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'tools/reference_engine_demos/postgresql_wire_parity'
DOCUMENT = ROOT / 'docs/en_US/postgresql_wire_parity.rst'
START = '.. parity-matrix-start'
END = '.. parity-matrix-end'
ORDER = ('postgresql', 'cockroachdb', 'yugabytedb')


def cell(result):
    if result is None:
        return 'not run'
    if result == 'supported':
        return 'yes'
    if result.get('status') == 'accepted_with_notice':
        return 'notice'
    if result.get('sqlstate') is None:
        return 'not kept'
    return f"no ({result['sqlstate']})"


def table():
    runs = {}
    for path in sorted(RESULTS.glob('*.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        runs[data['engine']] = (path.stem, data)
    engines = [engine for engine in ORDER if engine in runs]
    kinds = []
    for engine in engines:
        kinds += [kind for kind in runs[engine][1]['results']
                  if kind not in kinds]
    header = ['Probe'] + [runs[engine][0] for engine in engines]
    rows = [[kind] + [cell(runs[engine][1]['results'].get(kind))
                      for engine in engines] for kind in kinds]
    widths = [max(len(row[index]) for row in [header] + rows)
              for index in range(len(header))]
    rule = '  '.join('=' * width for width in widths)

    def line(row):
        return '  '.join(text.ljust(width)
                         for text, width in zip(row, widths)).rstrip()

    return '\n'.join([rule, line(header), rule] +
                     [line(row) for row in rows] + [rule])


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--check', action='store_true')
    options = parser.parse_args()
    text = DOCUMENT.read_text(encoding='utf-8')
    head, rest = text.split(START + '\n', 1)
    _old, tail = rest.split(END + '\n', 1)
    rendered = head + START + '\n\n' + table() + '\n\n' + END + '\n' + tail
    if options.check:
        if rendered != text:
            print('postgresql_wire_parity.rst matrix is out of date; run '
                  'tools/cdeadmin_postgresql_wire_parity_report.py',
                  file=sys.stderr)
            return 1
        return 0
    DOCUMENT.write_text(rendered, encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
