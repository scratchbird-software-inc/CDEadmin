"""Preserve native column clauses while translating explicit graphical edits."""
from copy import deepcopy
import json
import re
from .mysql_schema_plan import parts
from ..providers.mysql_family.mysql_catalog import identifier

TYPES = set('tinyint smallint mediumint int integer bigint decimal numeric float double real bit bool boolean date datetime timestamp time year char varchar binary varbinary tinyblob blob mediumblob longblob tinytext text mediumtext longtext enum set json geometry point linestring polygon multipoint multilinestring multipolygon geometrycollection vector'.split())


def tokens(source, mode):
    no_escape = 'NO_BACKSLASH_ESCAPES' in mode.split(',')
    ansi = 'ANSI_QUOTES' in mode.split(',')
    result = []
    i = 0
    while i < len(source):
        if source[i].isspace():
            i += 1
            continue
        start = i
        if source.startswith('/*', i):
            end = source.find('*/', i + 2)
            if end < 0: raise ValueError('Unclosed native column comment')
            i = end + 2
            kind = 'comment'
        elif source[i] in "'\"`":
            quote = source[i]
            kind = 'quoted'
            i += 1
            while i < len(source):
                if source[i] == '\\' and quote != '`' and not (quote == '"' and ansi) and not no_escape:
                    i += 2
                    continue
                if source[i] == quote:
                    if i + 1 < len(source) and source[i+1] == quote:
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            else: raise ValueError('Unclosed native column literal')
        elif source[i] == '(':
            # Reuse the quote-aware balanced table-list scanner for a single
            # argument/expression group; nested expressions remain opaque.
            from .mysql_table_clauses import table_layout
            layout = table_layout(source[i:], mode)
            i = len(source) - len(layout['suffix'])
            kind = 'group'
        else:
            match = re.match(r'[A-Za-z_][A-Za-z_0-9]*', source[i:])
            i += len(match.group()) if match else 1
            kind = 'word' if match else 'symbol'
        result.append((kind, source[start:i], start, i))
    return result


def datatype(value, mode):
    if not isinstance(value, str) or not value or len(value.encode('utf8')) > 16384 or '\x00' in value:
        raise ValueError('Graphical datatype requires bounded native type text')
    parsed = tokens(value, mode)
    if not parsed or parsed[0][0] != 'word' or parsed[0][1].lower() not in TYPES:
        raise ValueError('Unsupported graphical native datatype')
    index = 1
    if index < len(parsed) and parsed[index][0] == 'group': index += 1
    if parsed[0][1].lower() == 'double' and index < len(parsed) and parsed[index][1].upper() == 'PRECISION': index += 1
    for token in parsed[index:]:
        if token[0] != 'word' or token[1].upper() not in {'UNSIGNED', 'ZEROFILL'}:
            raise ValueError('Graphical datatype cannot contain column attributes or statements')
    return value.strip()


def literal(value, mode):
    if not isinstance(value, str) or '\x00' in value or len(value.encode('utf8')) > 1024:
        raise ValueError('Graphical column comment requires bounded text without NUL')
    if 'NO_BACKSLASH_ESCAPES' not in mode.split(','):
        value = value.replace('\\', '\\\\')
    return "'" + value.replace("'", "''") + "'"


def edit_clause(clause, changes, mode):
    parsed = tokens(clause, mode)
    if len(parsed) < 2 or parsed[0][0] != 'quoted' or parsed[1][0] != 'word':
        raise ValueError('Exact native quoted column definition is required')
    if 'datatype' in changes:
        end = 2
        if end < len(parsed) and parsed[end][0] == 'group': end += 1
        while end < len(parsed) and parsed[end][0] == 'word' and parsed[end][1].upper() in {'UNSIGNED', 'ZEROFILL', 'PRECISION'}: end += 1
        clause = clause[:parsed[1][2]] + datatype(changes['datatype'], mode) + clause[parsed[end-1][3]:]
    if 'nullable' in changes:
        if type(changes['nullable']) is not bool: raise ValueError('Graphical nullable must be boolean')
        parsed = tokens(clause, mode)
        match = next((i for i, token in enumerate(parsed) if token[0] == 'word' and token[1].upper() == 'NULL' and
                      not (i and parsed[i-1][1].upper() == 'DEFAULT')), None)
        desired = 'NULL' if changes['nullable'] else 'NOT NULL'
        if match is None: clause += ' ' + desired
        else:
            start = parsed[match-1][2] if match and parsed[match-1][1].upper() == 'NOT' else parsed[match][2]
            clause = clause[:start] + desired + clause[parsed[match][3]:]
    if 'description' in changes:
        parsed = tokens(clause, mode)
        match = next((i for i, token in enumerate(parsed) if token[0] == 'word' and token[1].upper() == 'COMMENT'), None)
        value = literal(changes['description'], mode)
        if match is None: clause += ' COMMENT ' + value
        else:
            if match + 1 >= len(parsed) or parsed[match+1][0] != 'quoted': raise ValueError('Ambiguous native column comment')
            clause = clause[:parsed[match+1][2]] + value + clause[parsed[match+1][3]:]
    return clause


def merge_fields(before, desired, mode, *, allow_new_columns=False):
    if type(allow_new_columns) is not bool: raise ValueError('New-column admission must be boolean')
    native = deepcopy(desired['native'])
    old_fields, new_fields = before.get('fields', {}), desired.get('fields', {})
    changes, additions = {}, []
    labels = [field.get('_label') for field in new_fields.values()]
    if any(not isinstance(label, str) for label in labels) or len(set(labels)) != len(labels):
        raise ValueError('Graphical field names must be unique')
    for uid, fields in new_fields.items():
        old = old_fields.get(uid)
        if set(fields.get('_property_names', [])) - {'uid', 'datatype', 'nullable', 'description'}:
            raise ValueError('Unsupported graphical field property')
        if old is None:
            if not allow_new_columns:
                raise ValueError('New or renamed graphical fields require explicit native reconciliation')
            if not isinstance(uid, str) or not uid or len(uid) > 4096:
                raise ValueError('New graphical field requires a bounded unique UID')
            if not 1 <= len(fields['_label']) <= 64: raise ValueError('Native column name requires 1 to 64 characters')
            column = identifier(fields['_label']) + ' ' + datatype(fields.get('datatype'), mode)
            column = edit_clause(column, {'nullable': fields.get('nullable', True),
                **({'description': fields['description']} if 'description' in fields else {})}, mode)
            additions.append((fields['_label'], column))
            if len(additions) > 128: raise ValueError('At most 128 new graphical columns per table')
            continue
        if fields.get('_label') != old.get('_label'):
            raise ValueError('New or renamed graphical fields require explicit native reconciliation')
        changed = {key: fields[key] for key in ('datatype', 'nullable', 'description') if key in fields and fields[key] != old.get(key)}
        if changed:
            expected = before['uid'] + ':' + json.dumps(old['_label'], ensure_ascii=False, separators=(',', ':'))
            if uid != expected: raise ValueError('Graphical field identity does not match its native column')
            changes[old['_label']] = changed
    if not changes and not additions: return native
    if before.get('kind') != 'table': raise ValueError('Graphical column changes require a native table')
    old_row = {'name': before['name'], 'native': before['native']}
    new_row = {'name': desired['name'], 'native': native}
    _layout, old_clauses, _order = parts(old_row, mode)
    layout, new_clauses, _order = parts(new_row, mode)
    replacements = {}
    for name, values in changes.items():
        key = ('column', name)
        if key not in old_clauses or key not in new_clauses:
            raise ValueError('Graphical column requires exact native clause identity')
        changed = edit_clause(old_clauses[key], values, mode)
        if new_clauses[key] not in {old_clauses[key], changed}:
            raise ValueError('Graphical and native column edits disagree')
        replacements[new_clauses[key]] = changed
    appended = []
    for name, clause in additions:
        key = ('column', name)
        if key in old_clauses:
            raise ValueError('New graphical UID cannot rebind an existing native column')
        if key in new_clauses:
            if new_clauses[key] != clause:
                raise ValueError('Graphical and native new-column definitions disagree')
        else:
            appended.append(clause)
    native['definition'] = layout['prefix'] + '(' + ','.join([
        *(replacements.get(clause.strip(), clause) for clause in layout['clauses']),
        *appended]) + ')' + layout['suffix']
    return native
