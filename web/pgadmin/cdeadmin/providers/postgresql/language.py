"""Offline PostgreSQL SQL grammar; no database execution or catalog binding."""
import hashlib
import json
import re

from pgadmin.cdeadmin.data_studio.language_tools import LanguageToolError


def analyze(source, *, script=False, standard_strings=None, backslash_quote=None):
    if not isinstance(source, str) or len(source.encode()) > 2 * 1024 * 1024:
        raise LanguageToolError('Source must be text no larger than 2 MiB')
    result = {
        'language_profile': 'postgresql-sql',
        'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
        'authority': 'postgresql-offline-grammar', 'grammar_valid': None,
        'syntax_valid': False, 'script_ready': False, 'statements': [],
        'diagnostics': [],
        'scope': 'Offline PostgreSQL SQL, SQL-body and PL/pgSQL grammar; catalog '
                 'resolution, permissions and other installed languages require native context.',
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
    if standard_strings not in {'on', 'off'}:
        issue('SESSION_MODE_REQUIRED',
              'Grammar checking requires the observed standard_conforming_strings setting.')
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
    patched = getattr(parser, 'CDEADMIN_PARSE_OPTIONS_REVISION', None) == 2
    parser_options = 64 | (32 if standard_strings == 'off' else 0) | (16 if backslash_quote == 'off' else 0)
    if not patched and (standard_strings == 'off' or backslash_quote == 'off'):
        issue('PARSER_UNAVAILABLE', 'Build the pinned PostgreSQL parser with native context options.')
        return result
    result['syntax_settings'] = {'standard_conforming_strings': standard_strings,
                                 'backslash_quote': backslash_quote}
    def parse_sql(text):
        return parser.parse_sql_json(text, parser_options) if patched else parser.parse_sql_json(text)
    result['scope'] = result['parser_version'] + '. ' + result['scope']
    try:
        tree = json.loads(parse_sql(source))
        if standard_strings == 'on' and backslash_quote != 'off':
            slices = parser.split(source, only_slices=True)
        else:
            # Native AST locations are UTF-8 byte offsets. The legacy splitter
            # has no option argument and would incorrectly reparse in ON mode.
            raw = source.encode('utf8')
            slices = []
            for statement in tree.get('stmts', []):
                at = statement.get('stmt_location', 0)
                length = statement.get('stmt_len', 0)
                end = at + length if length else len(raw)
                begin_text, text = raw[:at].decode('utf8'), raw[at:end].decode('utf8')
                start = len(begin_text) + len(text) - len(text.lstrip())
                slices.append(slice(start, len(begin_text) + len(text.rstrip())))
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
    result['sql_grammar_valid'] = True
    result['procedural_bodies'] = []
    for index, statement in enumerate(tree.get('stmts', [])):
        node = statement.get('stmt', {})
        definition = node.get('CreateFunctionStmt') or node.get('DoStmt')
        if definition is None:
            continue
        body_options = {item['DefElem']['defname']: item['DefElem'].get('arg')
                   for item in definition.get('options', definition.get('args', [])) if 'DefElem' in item}
        language = (body_options.get('language') or {}).get('String', {}).get('sval', 'plpgsql' if 'DoStmt' in node else '')
        language = language.lower()
        body = body_options.get('as')
        if isinstance(body, dict) and 'List' in body:
            body = body['List'].get('items')
        if isinstance(body, list):
            body = body[0].get('String', {}).get('sval') if len(body) == 1 else None
        elif isinstance(body, dict):
            body = body.get('String', {}).get('sval')
        # BEGIN ATOMIC SQL bodies are already part of the outer SQL AST.
        if body is None or language in {'c', 'internal'}:
            continue
        observation = {'ordinal': index + 1, 'language': language, 'grammar_valid': None}
        result['procedural_bodies'].append(observation)
        start = result['statements'][index]['start']
        if language not in {'sql', 'plpgsql'}:
            result['grammar_valid'] = None if result['grammar_valid'] is not False else False
            issue('BODY_GRAMMAR_UNAVAILABLE', 'No offline grammar is registered for this installed procedural language.', start)
            result['diagnostics'][-1]['severity'] = 'warning'
            continue
        try:
            body_flags = parser_options
            for item in definition.get('options', []):
                setting = item.get('DefElem', {}).get('arg', {}).get('VariableSetStmt', {})
                name = setting.get('name', '').lower()
                if name not in {'standard_conforming_strings', 'backslash_quote'}:
                    continue
                args = setting.get('args', [])
                value = args[0].get('A_Const', {}).get('sval', {}).get('sval', '').lower() if len(args) == 1 else ''
                bit = 32 if name == 'standard_conforming_strings' else 16
                if value in {'off', 'false', '0'}: body_flags |= bit
                elif value in {'on', 'true', '1', 'safe_encoding'}: body_flags &= ~bit
                elif setting.get('kind') != 'VAR_SET_CURRENT':
                    raise LanguageToolError('Routine parsing settings require an explicit native value')
            if language == 'plpgsql':
                if patched: parser.parse_plpgsql_json(result['statements'][index]['source'], parser_options, body_flags)
                else: parser.parse_plpgsql_json(result['statements'][index]['source'])
            else:
                if patched: parser.parse_sql_json(body, body_flags)
                else: parse_sql(body)
            observation['grammar_valid'] = True
        except LanguageToolError:
            result['grammar_valid'] = None if result['grammar_valid'] is not False else False
            issue('BODY_CONTEXT', 'Routine string settings require native context.', start)
            result['diagnostics'][-1]['severity'] = 'warning'
        except parser.ParseError as error:
            context_error = bool(re.search(r'unrecognized data type|does not exist|not a known variable|could not determine', str(error.args[0]), re.I))
            observation['grammar_valid'] = None if context_error else False
            if not context_error:
                result['grammar_valid'] = False
                result['syntax_valid'] = False
            elif result['grammar_valid'] is not False:
                result['grammar_valid'] = None
            issue('BODY_CONTEXT' if context_error else 'BODY_SYNTAX',
                  'Procedural checking needs native catalog context.' if context_error else
                  'The PostgreSQL procedural-body parser rejected the source.', start)
            result['diagnostics'][-1].update(severity='warning' if context_error else 'error', position_exact=False)
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
                    if kind == 'CreateFunctionStmt':
                        # SET options and SQL bodies here belong to the stored
                        # routine, not the connection framing this script.
                        continue
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
    result['script_ready'] = script and not any(row['severity'] == 'error' for row in result['diagnostics'])
    return result
