"""Typed native START_REPLICATION options and replication grammar."""
import re

from .temporary_slots import TemporarySlotError


def options(value):
    allowed = {'start_lsn', 'plugin_options', 'max_messages', 'max_capture_bytes',
               'max_duration_seconds', 'acknowledge_flush'}
    if set(value) - allowed:
        raise TemporarySlotError('Select exact native logical stream options')
    lsn = value.get('start_lsn', '0/0')
    if not isinstance(lsn, str) or not re.fullmatch(r'[0-9A-Fa-f]{1,8}/[0-9A-Fa-f]{1,8}', lsn):
        raise TemporarySlotError('Select an exact native logical stream start LSN')
    result = {'start_lsn': lsn.upper(), 'acknowledge_flush': value.get('acknowledge_flush', False)}
    if type(result['acknowledge_flush']) is not bool:
        raise TemporarySlotError('Native flush feedback requires an explicit boolean')
    for key, default in (('max_messages', 100), ('max_capture_bytes', 16777216), ('max_duration_seconds', 5)):
        selected = value.get(key, default)
        if selected is not None and (type(selected) is not int or not 1 <= selected <= 9223372036854775807):
            raise TemporarySlotError('Select a positive logical capture bound or no bound')
        result[key] = selected
    pairs = value.get('plugin_options', [])
    if not isinstance(pairs, list) or len(pairs) > 128:
        raise TemporarySlotError('Select a bounded native output plugin option list')
    result['plugin_options'] = []
    for pair in pairs:
        if not isinstance(pair, dict) or set(pair) != {'name', 'value'}:
            raise TemporarySlotError('Native output options require exact name/value pairs')
        name, selected = pair['name'], pair['value']
        try:
            valid = (isinstance(name, str) and 1 <= len(name.encode('utf8')) <= 63 and
                     '\0' not in name and '"' not in name and
                     (selected is None or isinstance(selected, str) and '\0' not in selected and
                      len(selected.encode('utf8')) <= 1048576))
        except UnicodeError:
            valid = False
        if not valid:
            raise TemporarySlotError('Select lossless native replication option identifiers and text values; the pinned parser cannot represent an embedded identifier quote')
        result['plugin_options'].append(dict(pair))
    return result


def statement(selected):
    from psycopg import sql
    command = sql.SQL('START_REPLICATION SLOT {} LOGICAL {}').format(
        sql.Identifier(selected['slot']), sql.SQL(selected['start_lsn']))
    if selected['plugin_options']:
        values = [sql.Identifier(pair['name']) if pair['value'] is None else
                  sql.SQL('{} {}').format(sql.Identifier(pair['name']), sql.Literal(pair['value']))
                  for pair in selected['plugin_options']]
        command += sql.SQL(' ({})').format(sql.SQL(', ').join(values))
    return command
