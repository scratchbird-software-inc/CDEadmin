"""Pinned SQLite AST binding in an isolated, empty native schema.

The internal rename helpers are version specific. They are enabled only in a
safe CLI child, never on a registered database or a user's connection.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import uuid

from flask import current_app, has_app_context

from ..sdk.tool_process import observe_process
from .sqlite_fts_rebind import equal, quote
from ..providers.sqlite.provider import PROFILE

SOURCE_ID = '2026-04-09 11:41:38 4525003a53a7fc63ca75c59b22c79608659ca12f0131f52c18637f829977f20b'
LIMIT = 24 * 1024 * 1024


def tokens(source):
    """Keep exact token spans; native SQLite determines their bindings."""
    result = []; i = 0
    while i < len(source):
        start = i; char = source[i]
        if char.isspace():
            i += 1; continue
        if source.startswith('--', i):
            end = source.find('\n', i + 2); i = len(source) if end < 0 else end + 1
            continue
        if source.startswith('/*', i):
            end = source.find('*/', i + 2)
            if end < 0: raise ValueError('Incomplete SQLite schema comment')
            i = end + 2; continue
        if char in "'\"`[":
            close = ']' if char == '[' else char; i += 1
            while i < len(source):
                if source[i] == close:
                    i += 1
                    if close != ']' and i < len(source) and source[i] == close:
                        i += 1; continue
                    break
                i += 1
            else: raise ValueError('Incomplete SQLite schema quoted token')
        elif char.isalnum() or char in '_$' or ord(char) >= 128:
            i += 1
            while i < len(source) and (source[i].isalnum() or source[i] in '_$' or ord(source[i]) >= 128): i += 1
        else: i += 1
        result.append((start, i, source[start:i]))
    return result


def shell_statement(source):
    """Remove shell command boundaries outside SQL quoted tokens.

    Native execute() has already admitted exactly one declaration. Comments
    and external newlines must not become CLI dot commands after its terminator.
    Quoted contents, including their embedded newlines, remain byte exact.
    """
    result = []; end = 0
    for start, stop, token in tokens(source):
        if start != end: result.append(' ')
        result.append(token); end = stop
    return ''.join(result).rstrip(';') + ';'


def text(value):
    return "CAST(X'" + value.encode('utf8').hex() + "' AS TEXT)"


def program():
    configured = (current_app.config.get('CDEADMIN_SQLITE_BINARY') if has_app_context() else None)
    configured = configured or os.environ.get('CDEADMIN_SQLITE_BINARY')
    suffix = '.exe' if os.name == 'nt' else ''
    candidates = [configured] if configured else [
        *(str(Path(prefix) / 'bin' / ('sqlite3' + suffix)) for prefix in dict.fromkeys((sys.prefix, sys.base_prefix))),
        shutil.which('sqlite3' + suffix)]
    selected = next((Path(path).resolve() for path in candidates if path and Path(path).is_file()), None)
    if selected is None: raise ValueError('The pinned native SQLite schema rewriter is unavailable on this application host')
    return selected


def mappings(connection, selected, rebindings):
    relations = []
    for (name,) in connection.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        columns = connection.execute('PRAGMA main.table_xinfo(' + quote(name) + ')').fetchall()
        relations.append({'original': name, 'current': name,
                          'columns': [{'index': row[0], 'original': row[1], 'current': row[1]} for row in columns]})
    for item in selected:
        found = [row for row in relations if equal(row['current'], item['table'])]
        if len(found) != 1: raise ValueError('Native rename relation identity is ambiguous')
        row = found[0]
        if item['kind'] == 'table': row['current'] = item['to']
        else:
            fields = [field for field in row['columns'] if equal(field['current'], item['from'])]
            if len(fields) != 1: raise ValueError('Native rename column identity is ambiguous')
            fields[0]['current'] = item['to']
    for rebind in rebindings:
        row = next(row for row in relations if row['original'] == rebind['source_name'])
        for change in rebind['column_renames']:
            fields = [field for field in row['columns'] if equal(field['current'], change['from'])]
            if len(fields) != 1: raise ValueError('Native FTS rename column identity is ambiguous')
            fields[0]['current'] = change['to']
    result = []
    for row in relations:
        if row['original'] != row['current']:
            result.append(('table', row['original'], None, row['current']))
        for field in row['columns']:
            if field['original'] != field['current']:
                result.append(('column', row['original'], field['index'], field['current']))
    return result


def _admitted_runtime(connection):
    """The connection runs on the loaded library inside the profile range.

    sqlite_version() through SQL can be redefined by a session, so the
    loaded library's version is the authority and must agree with it.
    """
    import sqlite3
    runtime = sqlite3.sqlite_version
    observed = connection.execute('SELECT sqlite_version()').fetchone()[0]
    return observed == runtime and PROFILE.accepts_runtime_version(runtime)

def rewrite(connection, declarations, selected, rebindings, *, view_columns=(),
            schema_declarations=None,native_targets=(),edits_out=None):
    if not _admitted_runtime(connection):
        raise ValueError(
            'The schema binding connection is not an admitted SQLite runtime')
    dependencies = [row for row in declarations if row['kind'] in {'view', 'trigger'}]
    changes = mappings(connection, selected, rebindings)
    changes.extend(native_targets)
    views={row['name'] for row in dependencies if row['kind']=='view'}
    for name,index,replacement in view_columns:
        if name not in views or type(index) is not int or index<0 or not isinstance(replacement,str):
            raise ValueError('Native derived-view binding identity is invalid')
        columns=connection.execute('PRAGMA main.table_xinfo('+quote(name)+')').fetchall()
        if index>=len(columns) or columns[index][0]!=index:
            raise ValueError('Native derived-view binding ordinal changed')
        if columns[index][1]!=replacement:changes.append(('column',name,index,replacement))
    executable = program(); before = hashlib.sha256(executable.read_bytes()).hexdigest()
    nonce = uuid.uuid4().hex; marker = '__cde_native_binding_' + nonce
    table = quote('__cde_bind_' + nonce)
    cache = quote('__cde_view_columns_' + nonce)
    probes = []; expressions = ['CREATE TEMP TABLE ' + table + '(probe,rewritten,version,source_id);',
        'CREATE TEMP TABLE ' + cache + '(owner,cid,name);']
    # SQLite computes view columns lazily. Its internal column renamer checks
    # nCol before parsing a dependent statement, so populate the native cache
    # after the last schema DDL and before requesting view-column bindings.
    expressions.extend('INSERT INTO '+cache+' SELECT '+text(row['name'])+',cid,name FROM pragma_table_xinfo('+text(row['name'])+",'main');"
        for row in dependencies if row['kind']=='view')
    expressions.append('INSERT INTO ' + table + " SELECT -1," + text(nonce) + ',sqlite_version(),sqlite_source_id();')
    for row_index, row in enumerate(dependencies):
        source = row['native']['ddl']
        if marker in source: raise ValueError('Native rewrite marker collision')
        for kind, name, index, replacement in changes:
            number = len(probes); probes.append((row_index, source, replacement))
            args = ([text(source), text(row['kind']), text(row['name']), text('main'), text(name), str(index), text(marker), '1', '0']
                    if kind == 'column' else [text('main'), text(row['kind']), text(row['name']), text(source), text(name), text(marker), '0'])
            expressions.append('INSERT INTO ' + table + ' SELECT ' + str(number) + ',sqlite_rename_' + kind + '(' + ','.join(args) + '),NULL,NULL;')
    query = "SELECT json_group_array(json_object('probe',probe,'rewritten',rewritten,'version',version,'source_id',source_id)) FROM (SELECT * FROM " + table + ' ORDER BY probe);'
    materialized=declarations if schema_declarations is None else schema_declarations
    script = '.testctrl internal_functions\n' + '\n'.join(shell_statement(row['native']['ddl']) for row in materialized) + '\n' + '\n'.join(expressions) + '\n.mode list\n' + query + '\n'
    if len(script.encode('utf8')) > LIMIT: raise ValueError('Native schema binding request is too large')
    try:
        with tempfile.TemporaryDirectory(prefix='cde-sqlite-bind-') as directory:
            init = Path(directory) / 'empty-init'; init.write_bytes(b'')
            observed = observe_process([str(executable), '-safe', '-batch', '-bail', '-init', str(init), ':memory:'],
                workspace=directory, environment=dict(os.environ), input_bytes=script.encode('utf8'), input_stream=None,
                timeout=30, capture_limit=LIMIT)
    except OSError:
        raise ValueError('The native SQLite schema rewriter could not start on this application host') from None
    if (observed['return_code'] != 0 or not observed['cleanup_confirmed'] or
            observed.get('stdout_bytes', 0) > LIMIT or observed.get('output_collection_incomplete')):
        raise ValueError('Native SQLite schema binding refused or did not finish on this application host')
    if hashlib.sha256(executable.read_bytes()).hexdigest() != before:
        raise ValueError('The native SQLite schema rewriter changed during execution')
    try:
        replies = json.loads(observed['stdout'])
        header = replies[0]
        if (header != {'probe': -1, 'rewritten': nonce, 'version': '3.53.0', 'source_id': SOURCE_ID} or len(replies) != len(probes) + 1): raise ValueError()
    except (ValueError, TypeError, KeyError, IndexError):
        raise ValueError('Native SQLite schema binding returned an unqualified reply') from None
    edits = [{} for row in dependencies]
    for number, reply in enumerate(replies[1:]):
        row_index, source, replacement = probes[number]
        rewritten = reply.get('rewritten')
        if reply.get('probe') != number or not isinstance(rewritten, str):
            raise ValueError('Native SQLite schema binding omitted a dependency')
        original, changed = tokens(source), tokens(rewritten)
        if len(original) != len(changed): raise ValueError('Native SQLite schema binding changed token structure')
        previous_original = previous_changed = 0
        for (start, stop, old), (new_start, new_stop, new) in zip(original, changed):
            if source[previous_original:start] != rewritten[previous_changed:new_start]:
                raise ValueError('Native SQLite schema binding changed source outside an identifier')
            if old != new:
                if new != quote(marker): raise ValueError('Native SQLite schema binding changed an unrelated token')
                value = quote(replacement)
                if start in edits[row_index] and edits[row_index][start] != (stop, value):
                    raise ValueError('Native SQLite schema binding found overlapping identities')
                edits[row_index][start] = (stop, value)
            previous_original, previous_changed = stop, new_stop
        if source[previous_original:] != rewritten[previous_changed:]: raise ValueError('Native SQLite schema binding changed source suffix')
    definitions = []
    for row, changes in zip(dependencies, edits):
        if edits_out is not None:edits_out[(row['kind'],row['name'])]=dict(changes)
        source = row['native']['ddl']
        for start, (stop, value) in sorted(changes.items(), reverse=True): source = source[:start] + value + source[stop:]
        definitions.append((row, source))
    runtime = {'authority': 'sqlite-3.53.0-native-rename-ast', 'path': str(executable), 'sha256': before,
               'version': '3.53.0', 'source_id': SOURCE_ID, 'execution_host': socket.getfqdn(),
               'scope': 'isolated-empty-schema; no registered file or user connection'}
    return definitions, runtime
