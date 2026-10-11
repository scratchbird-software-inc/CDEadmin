"""Lossless Firebird 5 RDB$TRIGGER_TYPE decoding (native constants.h)."""
from .columns import integer

MASK = 3 << 13
DDL_ACTIONS = {
    1: 'CREATE TABLE', 2: 'ALTER TABLE', 3: 'DROP TABLE',
    4: 'CREATE PROCEDURE', 5: 'ALTER PROCEDURE', 6: 'DROP PROCEDURE',
    7: 'CREATE FUNCTION', 8: 'ALTER FUNCTION', 9: 'DROP FUNCTION',
    10: 'CREATE TRIGGER', 11: 'ALTER TRIGGER', 12: 'DROP TRIGGER',
    16: 'CREATE EXCEPTION', 17: 'ALTER EXCEPTION', 18: 'DROP EXCEPTION',
    19: 'CREATE VIEW', 20: 'ALTER VIEW', 21: 'DROP VIEW',
    22: 'CREATE DOMAIN', 23: 'ALTER DOMAIN', 24: 'DROP DOMAIN',
    25: 'CREATE ROLE', 26: 'ALTER ROLE', 27: 'DROP ROLE',
    28: 'CREATE INDEX', 29: 'ALTER INDEX', 30: 'DROP INDEX',
    31: 'CREATE SEQUENCE', 32: 'ALTER SEQUENCE', 33: 'DROP SEQUENCE',
    34: 'CREATE USER', 35: 'ALTER USER', 36: 'DROP USER',
    37: 'CREATE COLLATION', 38: 'DROP COLLATION', 39: 'ALTER CHARACTER SET',
    40: 'CREATE PACKAGE', 41: 'ALTER PACKAGE', 42: 'DROP PACKAGE',
    43: 'CREATE PACKAGE BODY', 44: 'DROP PACKAGE BODY',
    45: 'CREATE MAPPING', 46: 'ALTER MAPPING', 47: 'DROP MAPPING',
}


def action(value):
    value = int(integer(value, 1, (1 << 63) - 1, 'Trigger event mask'))
    family = value & MASK
    if family == 0:
        slots = [((value + 1) >> shift) & 3 for shift in (1, 3, 5)]
        used = [item for item in slots if item]
        if value > 126 or not used or slots != used + [0] * (3 - len(used)) or len(set(used)) != len(used):
            raise ValueError('Invalid native DML trigger event mask')
        return ('AFTER' if (value + 1) & 1 else 'BEFORE') + ' ' + ' OR '.join(
            {1: 'INSERT', 2: 'UPDATE', 3: 'DELETE'}[item] for item in used)
    if family == 1 << 13:
        event = value & ~MASK
        events = ['CONNECT', 'DISCONNECT', 'TRANSACTION START', 'TRANSACTION COMMIT', 'TRANSACTION ROLLBACK']
        if event >= len(events):
            raise ValueError('Unknown native database trigger event')
        return 'ON ' + events[event]
    if family == 2 << 13:
        bits = value & ~MASK & ~1
        prefix = 'AFTER ' if value & 1 else 'BEFORE '
        if bits == ((1 << 63) - 1) & ~MASK & ~1:
            return prefix + 'ANY DDL STATEMENT'
        known = sum(1 << bit for bit in DDL_ACTIONS)
        if not bits or bits & ~known:
            raise ValueError('Unknown native DDL trigger event bits')
        return prefix + ' OR '.join(name for bit, name in DDL_ACTIONS.items() if bits & (1 << bit))
    raise ValueError('Unknown native trigger family')
