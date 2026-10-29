#!/usr/bin/env python3
##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Merge per-version SQLite dialect inventories into one versioned table.

Owner direction, 2026-10-29: grammar, keyword and function tables track
features added and removed across SQLite versions, older and newer, until an
older version is explicitly retired. Each input is the output of
``generate_sqlite_dialect_inventory.py --version X`` for one tracked version.

Every record is keyed by its native identity, not its positional item id.
``introduced_in`` is the first tracked version where the record is present
and ``introduced_after`` the tracked version before it, so the real change
lies in ``(introduced_after, introduced_in]``; ``removed_in`` likewise is the
first tracked version where a previously present record is absent. Grammar
production text (``commands``/``statements``) is tracked as presence only:
reformatting and renamed nonterminals make text differences that are not
feature differences.

Retirement (``--retire-below``) drops tracked versions below the new floor
and records that exist only in them, and raises the floor declared in the
SQLite UI descriptor, which stays the single source of the supported range.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


SCHEMA = 'cdeadmin.engine-dialect-versions.v1'
ROOT = Path(__file__).resolve().parents[2]
DESCRIPTOR = (ROOT / 'web/pgadmin/cdeadmin/ui_descriptors/sqlite/'
              'capabilities.json')
REFERENCE_VERSION = '3.53.0'
PRESENCE_ONLY = frozenset({'commands', 'statements'})


def version_key(text):
    return tuple(int(part) for part in str(text).split('.'))


def record_key(inventory, record):
    """Return the native identity of one inventory record."""
    if inventory == 'functions':
        return '{}|{}|{}'.format(
            record['function_name'], record['argument_count'],
            record['encoding'])
    if inventory == 'data_types':
        return '{}|{}'.format(
            record['native_name'], bool(record.get('strict_table_type')))
    return record['native_name']


def _without_position(record):
    value = copy.deepcopy(record)
    value.pop('item_id', None)
    return value


def task_proof(live_paths, versions):
    """Summarise live dialect-task qualification per tracked version.

    Each input is ``cdeadmin_relational_provider_live_verify.py --engine
    sqlite --dialect-qualification`` output from a runtime of exactly that
    version. A task is proven for a version only when it executed live there.
    """
    proof = {}
    for path in live_paths:
        document = json.loads(path.read_text(encoding='utf-8'))
        version = document.get('observed_runtime_version')
        if version not in versions:
            raise RuntimeError(f'{path.name}: {version} is not tracked')
        if version in proof:
            raise RuntimeError(f'two live evidence files for {version}')
        if document.get('unactivated_dialect_qualification') is not True or (
                document.get('credential_values_exported') is not False):
            raise RuntimeError(f'{path.name} is not dialect qualification')
        evidence = document['object_experience_evidence']
        proof[version] = {
            'evidence': path.relative_to(ROOT).as_posix(),
            'evidence_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'proven_tasks': sorted(document['qualified_dialect_task_ids']),
            'unproven_tasks': sorted(document['missing_dialect_task_ids']),
            'operation_failures': dict(sorted(
                evidence.get('operation_failures', {}).items())),
        }
    return proof


def merge(documents, reference=REFERENCE_VERSION):
    """Merge ``{version: inventory document}`` into the versioned table."""
    versions = sorted(documents, key=version_key)
    if reference not in documents:
        raise RuntimeError(f'reference version {reference} is not tracked')
    for version, document in documents.items():
        if document.get('reference_version') != version or (
                document.get('completeness', {}).get('runtime_version') !=
                version):
            raise RuntimeError(f'inventory for {version} has another identity')
    names = sorted({name for document in documents.values()
                    for name in document['inventories']})
    inventories = {}
    for name in names:
        entries = {}
        order = []
        for version in versions:
            seen = set()
            for record in documents[version]['inventories'].get(name, ()):
                key = record_key(name, record)
                if key in seen:
                    raise RuntimeError(
                        f'{name} key {key!r} is not unique in {version}')
                seen.add(key)
                if key not in entries:
                    entries[key] = {'key': key, 'records': {}}
                    order.append(key)
                entries[key]['records'][version] = copy.deepcopy(record)
        merged = []
        for key in order:
            entry = entries[key]
            present = [v for v in versions if v in entry['records']]
            first = present[0]
            first_index = versions.index(first)
            removed = next((v for v in versions[first_index:]
                            if v not in entry['records']), None)
            later = [v for v in versions[versions.index(removed):]
                     if v in entry['records']] if removed else []
            if later:
                raise RuntimeError(
                    f'{name} {key!r} disappears in {removed} and returns in '
                    f'{later[0]}; record it explicitly before merging')
            newest = present[-1]
            base = _without_position(entry['records'][newest])
            variants = {
                v: _without_position(entry['records'][v]) for v in present
                if _without_position(entry['records'][v]) != base
            }
            item = {
                'key': key,
                'native_name': base['native_name'],
                'present_in': present,
                'introduced_in': first,
                'introduced_after': (
                    versions[first_index - 1] if first_index else None),
                'removed_in': removed,
                'item_ids': {v: entry['records'][v]['item_id']
                             for v in present},
                'record': base,
            }
            if name in PRESENCE_ONLY:
                item['tracking'] = 'presence_only'
            if variants:
                item['record_by_version'] = variants
            merged.append(item)
        inventories[name] = merged
    _mark_signature_changes(inventories.get('functions', ()))
    return {
        'schema': SCHEMA,
        'engine_id': 'sqlite',
        'reference_version': reference,
        'tracked_versions': versions,
        'range_authority': (
            'web/pgadmin/cdeadmin/ui_descriptors/sqlite/capabilities.json '
            'version_range'),
        'interval_semantics': (
            'A change lies in (introduced_after, introduced_in] and '
            '(last present, removed_in]; precision is limited to the '
            'tracked versions.'),
        'sources': {
            version: {
                'inventory_id': documents[version]['inventory_id'],
                'source_evidence': documents[version]['source_evidence'],
                'runtime_modules':
                    documents[version]['completeness']['runtime_modules'],
                'runtime_compile_options': documents[version][
                    'completeness']['runtime_compile_options'],
                'inventory_counts':
                    documents[version]['completeness']['inventory_counts'],
            }
            for version in versions
        },
        'inventories': inventories,
        'derived': {'function_names': _function_names(
            inventories.get('functions', ()), versions)},
    }


def _mark_signature_changes(functions):
    """Tell a changed argument-count notation apart from a removal.

    ``PRAGMA function_list`` reports some functions under a different
    argument count in later releases (for example ``coalesce`` as -1, then
    -4). The (name, encoding) pair stays available across that change.
    """
    by_name = {}
    for item in functions:
        record = item['record']
        by_name.setdefault(
            (record['function_name'], record['encoding']), []).append(item)
    for items in by_name.values():
        for gone in items:
            if gone['removed_in'] is None:
                continue
            successors = [
                other['key'] for other in items
                if other['introduced_in'] == gone['removed_in']]
            if successors:
                gone['signature_changed_in'] = gone['removed_in']
                gone['signature_successors'] = successors


def _function_names(functions, versions):
    """Availability of each function name, whatever its signatures."""
    present = {}
    for item in functions:
        name = item['record']['function_name']
        present.setdefault(name, set()).update(item['present_in'])
    result = []
    for name in sorted(present):
        tracked = [v for v in versions if v in present[name]]
        first = versions.index(tracked[0])
        removed = next((v for v in versions[first:] if v not in present[name]),
                       None)
        result.append({
            'function_name': name,
            'present_in': tracked,
            'introduced_in': tracked[0],
            'introduced_after': versions[first - 1] if first else None,
            'removed_in': removed,
        })
    return result


def inventory_for(versioned, version):
    """Rebuild one tracked version's inventories exactly, in source order."""
    if version not in versioned['tracked_versions']:
        raise KeyError(f'{version} is not a tracked SQLite version')
    result = {}
    for name, items in versioned['inventories'].items():
        rows = []
        for item in items:
            if version not in item['present_in']:
                continue
            record = copy.deepcopy(item.get('record_by_version', {}).get(
                version, item['record']))
            record['item_id'] = item['item_ids'][version]
            rows.append(record)
        rows.sort(key=lambda row: row['item_id'])
        result[name] = rows
    return result


def retire_below(versioned, floor):
    """Drop tracked versions below ``floor`` and records only they held."""
    kept = [v for v in versioned['tracked_versions']
            if version_key(v) >= version_key(floor)]
    if not kept or versioned['reference_version'] not in kept:
        raise RuntimeError('retirement would remove the reference version')
    documents = {}
    for version in kept:
        documents[version] = {
            'reference_version': version,
            'inventory_id': versioned['sources'][version]['inventory_id'],
            'source_evidence': versioned['sources'][version][
                'source_evidence'],
            'completeness': {
                'runtime_version': version,
                'runtime_modules': versioned['sources'][version][
                    'runtime_modules'],
                'runtime_compile_options': versioned['sources'][version][
                    'runtime_compile_options'],
                'inventory_counts': versioned['sources'][version][
                    'inventory_counts'],
            },
            'inventories': inventory_for(versioned, version),
        }
    return merge(documents, versioned['reference_version'])


def _write(path, document):
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + '\n',
                    encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', action='append', type=Path,
                        default=[], help='per-version inventory JSON')
    parser.add_argument('--live', action='append', type=Path, default=[],
                        help='per-version dialect qualification evidence')
    parser.add_argument('--versioned', type=Path,
                        help='existing versioned table (for retirement)')
    parser.add_argument('--retire-below',
                        help='new floor; owner decision only')
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    if options.retire_below:
        if options.versioned is None:
            parser.error('--retire-below needs --versioned')
        existing = json.loads(options.versioned.read_text(encoding='utf-8'))
        document = retire_below(existing, options.retire_below)
        document['task_proof'] = {
            version: proof for version, proof in
            existing.get('task_proof', {}).items()
            if version in document['tracked_versions']}
        descriptor = json.loads(DESCRIPTOR.read_text(encoding='utf-8'))
        descriptor['version_range']['minimum'] = options.retire_below
        descriptor['version_range']['tested'] = [
            v for v in descriptor['version_range'].get('tested', [])
            if version_key(v) >= version_key(options.retire_below)]
        # Keep the descriptor's own key order and layout.
        DESCRIPTOR.write_text(json.dumps(descriptor, indent=2) + '\n',
                              encoding='utf-8')
    else:
        documents = {}
        for path in options.inventory:
            document = json.loads(path.read_text(encoding='utf-8'))
            documents[document['reference_version']] = document
        document = merge(documents)
        document['task_proof'] = task_proof(
            [path.resolve() for path in options.live],
            document['tracked_versions'])
    _write(options.output, document)
    print(json.dumps({
        'tracked_versions': document['tracked_versions'],
        'counts': {name: len(items)
                   for name, items in document['inventories'].items()},
    }, indent=2))


if __name__ == '__main__':
    main()
