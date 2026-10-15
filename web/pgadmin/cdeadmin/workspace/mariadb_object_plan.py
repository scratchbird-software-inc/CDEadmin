"""MariaDB native object identities, replacements and explicit sequence options."""
import re
from ..providers.mysql_family.mariadb_catalog import identifier
from .firebird_catalog_import import _equal

TOKEN = r'(?:`(?:``|[^`])+`|"(?:""|[^"])+"|(?:[^\W\d]|\$)(?:\w|\$)*)'
HEADER = re.compile(r'^\s*CREATE\s+(?:OR\s+REPLACE\s+)?'
    r'(?:ALGORITHM\s*=\s*(?:UNDEFINED|MERGE|TEMPTABLE)\s+)?'
    r'(?:DEFINER\s*=\s*'+TOKEN+r'\s*@\s*'+TOKEN+r'\s+)?'
    r'(?:SQL\s+SECURITY\s+(?:DEFINER|INVOKER)\s+)?'
    r'(?P<kind>PACKAGE\s+BODY|PACKAGE|PROCEDURE|FUNCTION|TRIGGER|EVENT|SEQUENCE|VIEW)\s+'
    r'(?P<first>'+TOKEN+r')(?:\s*\.\s*(?P<second>'+TOKEN+r'))?(?=\s|\()', re.I)
TRIGGER = re.compile(r'^\s+(?P<timing>BEFORE|AFTER)\s+(?P<event>INSERT|UPDATE|DELETE)\s+ON\s+'
    r'(?P<first>'+TOKEN+r')(?:\s*\.\s*(?P<second>'+TOKEN+r'))?\s+FOR\s+EACH\s+ROW\b', re.I)
REPLACEABLE = frozenset({'procedure', 'function', 'package', 'package-body', 'trigger'})
KINDS = REPLACEABLE | {'view', 'event', 'sequence', 'database'}


def unquote(value):
    return value[1:-1].replace(value[0]*2, value[0]) if value[0] in '`"' else value


def names(match):
    return [unquote(match[key]) for key in ('first', 'second') if match[key] is not None]


def definition(row, database):
    source = row['native'].get('definition')
    if not isinstance(source, str) or not source or '\0' in source:
        raise ValueError('Exact native object definition is required')
    match = HEADER.match(source)
    if (not match or re.sub(r'\s+', '-', match['kind'].lower()) != row['kind'] or
            names(match) not in ([row['name']], [database, row['name']])):
        raise ValueError('Native definition header disagrees with object identity')
    return source, match


def compile_database(before, after, operation, database):
    intent = after['native'].get('mariadb_change')
    if (operation != 'alter' or before is None or after['name'] != database or
            not isinstance(intent, dict) or intent.get('action') != 'alter-options' or
            set(intent)-{'action', 'character_set', 'collation'} or len(intent) < 2 or
            not _equal({key: before['native'].get(key) for key in ('definition', 'definition_context')},
                {key: after['native'].get(key) for key in ('definition', 'definition_context')})):
        raise ValueError('Database changes require explicit native alter-options intent; lifecycle is separate')
    clauses = []
    for key, prefix in [('character_set', 'DEFAULT CHARACTER SET '), ('collation', 'DEFAULT COLLATE ')]:
        if key in intent:
            value = intent[key]
            if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,64}', value):
                raise ValueError('Exact native charset/collation identity is required')
            clauses.append(prefix+identifier(value))
    return 'ALTER DATABASE '+identifier(database)+' '+' '.join(clauses)


def compile_sequence(before, after, operation, database):
    source, match = definition(after, database)
    target = identifier(database)+'.'+identifier(after['name'])
    intent = after['native'].get('mariadb_change')
    if operation == 'create' and before is None and not intent:
        return source[:match.start('first')]+target+source[match.end():]
    if operation == 'drop' and intent == {'action': 'drop', 'confirmation': after['name']}:
        return 'DROP SEQUENCE '+target
    if (operation != 'alter' or before is None or not isinstance(intent, dict) or
            intent.get('action') != 'alter-options' or set(intent)-{
                'action', 'start', 'minvalue', 'maxvalue', 'increment', 'cache', 'cycle', 'restart', 'confirmation'} or
            len(set(intent)-{'action', 'confirmation'}) < 1 or
            not _equal({key: before['native'].get(key) for key in ('definition', 'definition_context')},
                {key: after['native'].get(key) for key in ('definition', 'definition_context')})):
        raise ValueError('Sequence ALTER requires explicit options with unchanged native definition/context')
    clauses = []
    for key, prefix in [('start', 'START WITH '), ('minvalue', 'MINVALUE '), ('maxvalue', 'MAXVALUE '),
            ('increment', 'INCREMENT BY '), ('cache', 'CACHE '), ('restart', 'RESTART WITH ')]:
        if key in intent:
            value = intent[key]
            if type(value) is not int or not -(2**63) <= value <= 2**64-1:
                raise ValueError('Sequence options require exact native bounded integers')
            clauses.append(prefix+str(value))
    if 'cycle' in intent:
        if type(intent['cycle']) is not bool: raise ValueError('Sequence cycle option must be boolean')
        clauses.append('CYCLE' if intent['cycle'] else 'NOCYCLE')
    if 'restart' in intent:
        if intent.get('confirmation') != after['name']:
            raise ValueError('Sequence restart requires exact native name confirmation')
    elif 'confirmation' in intent:
        raise ValueError('Sequence confirmation applies only to an explicit restart')
    return 'ALTER SEQUENCE '+target+' '+' '.join(clauses)


def compile_object(before, after, operation, database, trigger_order=None):
    kind = after['kind']; intent = after['native'].get('mariadb_change')
    if kind == 'database': return compile_database(before, after, operation, database)
    if kind == 'sequence': return compile_sequence(before, after, operation, database)
    source, match = definition(after, database)
    target = identifier(database)+'.'+identifier(after['name'])
    if operation == 'drop' and before is not None and intent == {'action': 'drop', 'confirmation': after['name']}:
        return 'DROP '+kind.upper().replace('-', ' ')+' '+target
    if operation == 'create':
        if before is not None or intent: raise ValueError('Native creation requires an absent baseline and no replacement intent')
        command = 'CREATE'
    elif operation == 'alter' and before is not None:
        if kind in REPLACEABLE:
            if intent != {'action': 'replace', 'confirmation': after['name']}:
                raise ValueError('Native body/declaration replacement requires exact mariadb_change replace intent and name confirmation')
            command = 'CREATE OR REPLACE'
        elif kind in {'view', 'event'} and not intent:
            command = 'ALTER'
        else: raise ValueError('Unsupported native object alteration intent')
    else: raise ValueError('Native object operation disagrees with baseline presence')
    prefix = re.sub(r'^\s*CREATE(?:\s+OR\s+REPLACE)?\b', command, source[:match.start('first')], count=1, flags=re.I)
    tail = source[match.end():]
    if kind == 'event' and not re.match(r'^\s+ON\s+SCHEDULE\b', tail, re.I):
        raise ValueError('Exact native event schedule is required')
    if kind == 'trigger':
        trigger = TRIGGER.match(tail); facts = after['native'].get('trigger_identity', {})
        if (not trigger or facts.get('database') != database or
                names(trigger) not in ([facts.get('table')], [database, facts.get('table')]) or
                facts.get('timing') != trigger['timing'].upper() or facts.get('event') != trigger['event'].upper()):
            raise ValueError('Native trigger table/timing/event identity is inconsistent')
        # A single trigger must retain position 1. Multi-trigger ordering is
        # compiled only with an explicit named sibling from the reviewed plan.
        order = facts.get('action_order')
        sibling = trigger_order
        if type(order) is not int or order < 1: raise ValueError('Native trigger order is unavailable')
        if order > 1 and not sibling: raise ValueError('Native trigger sibling ordering must be resolved before replacement/creation')
        if sibling == {'single': True}:
            if order != 1: raise ValueError('Single native trigger must occupy position 1')
        elif sibling:
            if not isinstance(sibling, dict) or set(sibling) != {'position', 'name'} or sibling['position'] not in {'FOLLOWS', 'PRECEDES'}:
                raise ValueError('Exact native trigger sibling ordering is required')
            tail = tail[:trigger.end()]+' '+sibling['position']+' '+identifier(sibling['name'])+tail[trigger.end():]
        elif operation == 'alter':
            raise ValueError('Native trigger replacement requires reviewed sibling ordering or exclusive single-trigger proof')
    return prefix+target+tail
