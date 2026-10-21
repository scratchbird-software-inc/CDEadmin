"""Exact versioned MySQL server grammar without catalog binding or SQL I/O."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from ...data_studio.language_tools import analyze
from ...sdk.tool_process import observe_process
from ...sdk.relational import RelationalClientError
from ...sdk.tooling import ProviderToolRunner, tool_environment


def library(client):
    selected = os.environ.get('CDEADMIN_MYSQL_PARSER_LIBRARY')
    if selected:
        path = Path(selected).resolve(strict=True)
        if not path.is_file(): raise RelationalClientError('The configured MySQL native grammar library is unavailable')
        return path
    runner = getattr(client, '_tool_runner', None)
    declared = getattr(runner, '_allowlist', {}).get('mysql-shell')
    executable = ProviderToolRunner._resolve(declared) if declared else None
    if executable is None: return None
    executable = executable.resolve(strict=True)
    name = 'mysql_9.7.dll' if os.name == 'nt' else 'mysql_9.7.so'
    path = executable.parent.parent / 'lib' / 'mysqlsh' / 'yparser' / name
    return path.resolve(strict=True) if path.is_file() else None


def native(path, statements):
    worker = Path(__file__).with_name('mysql_parser_worker.py')
    request = {'version': '9.7.0', 'library': str(path), 'statements': statements}
    with tempfile.TemporaryDirectory(prefix='scratchrobin-mysql-parser-') as workspace:
        observed = observe_process([sys.executable, '-I', '-B', str(worker)], workspace=workspace,
            environment=tool_environment(sys.executable, workspace),
            input_bytes=json.dumps(request, ensure_ascii=True).encode('ascii'), input_stream=None,
            timeout=30, capture_limit=2 * 1024 * 1024)
    try:
        result = json.loads(observed['stdout'])
        if (observed['return_code'] != 0 or observed.get('timed_out') or observed.get('cleanup_confirmed') is not True or result.get('available') is not True or
                result.get('parser_version') != '9.7.0' or len(result['statements']) != len(statements)):
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        raise RelationalClientError('Native MySQL grammar validation is unavailable; no SQL was executed') from None
    result['execution_host_kind'] = 'application-host'
    result['worker_sha256'] = hashlib.sha256(worker.read_bytes()).hexdigest()
    result['library_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    result['process'] = {key: value for key, value in observed.items() if key not in {'stdout', 'stderr'}}
    return result


def validate(path, source, observation, script):
    if observation['version'].split('-')[0] != '9.7.0':
        raise RelationalClientError('The observed MySQL version differs from the native grammar profile')
    mode = observation['variables']['sql_mode']; modes = set(mode.split(','))
    result = analyze(source, 'mysql-sql', script=script, settings={
        'no_backslash_escapes': 'NO_BACKSLASH_ESCAPES' in modes,
        'ansi_quotes': 'ANSI_QUOTES' in modes, 'mysql_dollar_quotes': True})
    if not script:
        result['diagnostics'] = []
        if not source.strip():
            result['diagnostics'] = [{'code': 'EMPTY_SOURCE', 'message': 'Source is empty.',
                'severity': 'error', 'offset': 0, 'line': 1, 'column': 1}]
        elif '\x00' in source:
            result['diagnostics'] = [{'code': 'INVALID_SOURCE', 'message': 'SQL source contains NUL.',
                'severity': 'error', 'offset': source.index('\x00'), 'line': 1, 'column': 1}]
    result.update(authority='mysql-native-versioned-server-grammar', parser_version='9.7.0', sql_mode=mode,
        scope='Versioned native MySQL server grammar for UTF-8 editor text with the observed session SQL mode. No SQL is executed. Catalog names, privileges and quoted external language bodies are not validated.',
        original_diagnostics_preservation_qualified=True, original_session_commands_sent=0,
        original_diagnostics_preserved=True, original_session_catalog_binding_validated=False,
        external_language_bodies_parsed=False, sql_executed=False,
        parser_observation={**observation, 'thread_id': str(observation['thread_id']), 'connection_id': str(observation['connection_id'])})
    if result['diagnostics']: return result
    statements = result['statements'] if script else [{'source': source, 'start': 0, 'end': len(source), 'ordinal': 1}]
    checked = native(path, [{'source': item['source'], 'sql_mode': mode} for item in statements])
    valid = True
    for item, parsed in zip(statements, checked['statements']):
        valid = valid and parsed['sql_syntax_valid']
        encoded = item['source'].encode('utf8')
        # The client framer trims each statement; position offsets must include
        # precisely that whitespace within the original script segment.
        prefix = source[item['start']:item['end']]
        start = item['start'] + len(prefix) - len(prefix.lstrip())
        for diagnostic in parsed['diagnostics']:
            position = max(0, min(diagnostic['byte_offset'], len(encoded)))
            offset = start + len(encoded[:position].decode('utf8', errors='ignore'))
            hint = diagnostic['optimizer_hint']
            result['diagnostics'].append({'code': 'NATIVE_OPTIMIZER_HINT' if hint else 'NATIVE_SYNTAX',
                'message': 'Native parser reported an optimizer hint warning.' if hint else 'Native parser rejected the SQL syntax.',
                'severity': 'warning' if hint else 'error', 'offset': offset,
                'line': source.count('\n', 0, offset) + 1, 'column': offset - source.rfind('\n', 0, offset),
                'native_byte_offset': diagnostic['byte_offset'], 'native_byte_length': diagnostic['byte_length']})
    result.update(grammar_valid=valid, syntax_valid=valid, statements=statements, script_ready=bool(script and valid and statements),
        native_statements=[{'ordinal': item['ordinal'], 'grammar_valid': value['sql_syntax_valid'],
            'native_preparation': 'not_attempted', 'native_stage': 'versioned_server_grammar', 'catalog_binding_validated': False}
            for item, value in zip(statements, checked['statements'])],
        native_parser={key: value for key, value in checked.items() if key != 'statements'})
    return result
