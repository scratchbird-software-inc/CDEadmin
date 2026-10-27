"""Registered selectors for native AdminAPI SQL execution.

Native Shell owns contextual keyword resolution, exclusions, parallel execution,
per-instance errors and result formatting. This adapter preserves that behavior.
"""
from .mysql_binlog_archives import BinlogArchiveError

KEYWORDS = frozenset({'all', 'a', 'primary', 'p', 'secondaries', 's', 'read-replicas', 'rr'})


def selector(value):
    if isinstance(value, str):
        if value.lower() in KEYWORDS:
            return value
        raise BinlogArchiveError('Select a native topology keyword or registered instance array')
    if (not isinstance(value, list) or not 1 <= len(value) <= 128 or any(
            not isinstance(item, dict) or set(item) != {'server_id'} or
            type(item['server_id']) is not int or item['server_id'] <= 0 for item in value)):
        raise BinlogArchiveError('Select a bounded nonempty array of registered instance references')
    return value


def member_ids(arguments):
    values = [arguments[1]]
    if len(arguments) > 2 and isinstance(arguments[2], dict) and 'exclude' in arguments[2]:
        values.append(arguments[2]['exclude'])
    return {item['server_id'] for value in values if isinstance(value, list) for item in value}


def native_source():
    # Run inside native Shell after the existing registered-member identity
    # checks. Private passwords enter only the native in-memory URI formatter.
    return '''def native_fanout(arguments,prepared):
    def native_instances(value):
        if isinstance(value,str):return value
        return [shell.unparse_uri(prepared[item["server_id"]]) for item in value]
    arguments[1]=native_instances(arguments[1])
    if len(arguments)>2 and isinstance(arguments[2],dict) and "exclude" in arguments[2]:
        arguments[2]["exclude"]=native_instances(arguments[2]["exclude"])
    return arguments
'''
