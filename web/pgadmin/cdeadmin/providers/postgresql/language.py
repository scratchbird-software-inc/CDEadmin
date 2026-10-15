"""Offline PostgreSQL SQL grammar; no database execution or catalog binding."""
import hashlib
import json

from pgadmin.cdeadmin.data_studio.language_tools import LanguageToolError


def analyze(source, *, script=False, standard_strings=None):
    if not isinstance(source, str) or len(source.encode()) > 2 * 1024 * 1024:
        raise LanguageToolError('Source must be text no larger than 2 MiB')
    result = {
        'language_profile': 'postgresql-sql',
        'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
        'authority': 'postgresql-offline-grammar', 'grammar_valid': None,
        'syntax_valid': False, 'script_ready': False, 'statements': [],
        'diagnostics': [],
        'scope': 'Offline PostgreSQL SQL grammar only; catalog resolution, '
                 'permissions and quoted procedural bodies are not checked.',
    }

    def issue(code, message, offset=0):
        offset = max(0, min(len(source), offset))
        result['diagnostics'].append({
            'code': code, 'message': message, 'severity': 'error',
            'offset': offset, 'line': source.count('\n', 0, offset) + 1,
            'column': offset - source.rfind('\n', 0, offset),
        })

    if '\x00' in source:
        issue('INVALID_SOURCE', 'SQL source contains NUL.', source.index('\x00'))
        return result
    if standard_strings != 'on':
        issue('SESSION_MODE_REQUIRED',
              'Grammar checking requires standard_conforming_strings=on '
              'on this session.')
        return result
    try:
        import pglast
        from pglast import parser
    except ImportError:
        issue('PARSER_UNAVAILABLE', 'The PostgreSQL grammar package is unavailable.')
        return result
    version = parser.get_postgresql_version()
    result['parser_version'] = f'pglast {pglast.__version__}; PostgreSQL ' + '.'.join(map(str, version))
    if pglast.__version__ != 'v8.5' or version != (18, 6):
        issue('PARSER_UNAVAILABLE', 'The installed PostgreSQL parser revision is not qualified.')
        return result
    result['scope'] = result['parser_version'] + '. ' + result['scope']
    try:
        tree = json.loads(parser.parse_sql_json(source))
        slices = parser.split(source, only_slices=True)
    except parser.ParseError as exc:
        result['grammar_valid'] = False
        # In pinned 8.5, cursorpos (already characters) is passed through
        # Displacements as if it were bytes. Invert that conversion. A position
        # landing inside a multibyte character is ambiguous: report its range,
        # never manufacture a precise caret. EOF may have no supplied position.
        reported = exc.args[1] if len(exc.args) > 1 else None
        offset = len(source)
        end = offset
        if isinstance(reported, int):
            offset = min(len(source), len(source[:reported].encode()))
            width = len(source[reported:reported + 1].encode())
            end = min(len(source), offset + max(0, width - 1))
        issue('POSTGRESQL_SYNTAX', str(exc.args[0]), offset)
        result['diagnostics'][-1].update(offset_end=end,
                                         position_exact=end == offset)
        return result
    if len(slices) > 1000:
        issue('SCRIPT_LIMIT', 'Script exceeds 1000 statements.')
        return result
    if not slices:
        issue('EMPTY_SOURCE', 'Source has no SQL statements.')
        return result
    result['grammar_valid'] = True
    result['syntax_valid'] = True
    result['statements'] = [
        {'ordinal': i + 1, 'source': source[span],
         'start': span.start, 'end': span.stop}
        for i, span in enumerate(slices)]
    if script:
        # Inspect AST nodes, not words in comments or quoted routine bodies.
        pending = [tree]
        codes = set()
        while pending:
            node = pending.pop()
            if isinstance(node, list):
                pending.extend(node)
            elif isinstance(node, dict):
                for kind, value in node.items():
                    if kind == 'CopyStmt' and value.get('is_from') and not value.get('filename'):
                        codes.add('DATA_FRAMING_REQUIRED')
                    if kind == 'VariableSetStmt' and (
                            value.get('name', '').lower() in {
                                'standard_conforming_strings', 'client_encoding'}
                            or value.get('kind') == 'VAR_RESET_ALL'):
                        codes.add('SESSION_FRAMING_CHANGE')
                    if kind == 'DiscardStmt' and value.get('target') == 'DISCARD_ALL':
                        codes.add('SESSION_FRAMING_CHANGE')
                    # set_config can use computed setting names; it is not
                    # safe to infer that an arbitrary call preserves framing.
                    if kind == 'FuncCall' and any(
                            part.get('String', {}).get('sval', '').lower() == 'set_config'
                            for part in value.get('funcname', [])):
                        codes.add('SESSION_FRAMING_CHANGE')
                    pending.append(value)
        if 'DATA_FRAMING_REQUIRED' in codes:
            issue('DATA_FRAMING_REQUIRED', 'Use the native COPY/import tool for input streams.')
        if 'SESSION_FRAMING_CHANGE' in codes:
            issue('SESSION_FRAMING_CHANGE', 'Run parsing-setting changes outside a retained script.')
    result['script_ready'] = script and not result['diagnostics']
    return result
