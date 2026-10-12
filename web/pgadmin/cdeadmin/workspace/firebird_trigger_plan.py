"""Native trigger plans preserve attachment events and trigger identity."""
import re
from ..providers.firebird.character_metadata import identifier, literal, text
from ..providers.firebird.columns import integer
from ..providers.firebird.packages import source
from ..providers.firebird.trigger_types import action, MASK
from .firebird_routine_plan import flag
from .firebird_view_plan import dependencies

FIELDS = {'relation', 'trigger_type', 'inactive', 'position', 'metadata_source',
          'description', 'sql_security', 'entrypoint', 'engine_name'}
DERIVED = {'administration', 'valid_blr'}


def model(row):
    native = row['native']
    if native.get('constraint_owner'):
        raise ValueError('Constraint-owned triggers require their owning constraint operation')
    missing = FIELDS - {'description'} - native.keys()
    if missing:
        raise ValueError('Exact trigger metadata is missing: ' + ', '.join(sorted(missing)))
    event = int(integer(native['trigger_type'], 1, (1 << 63) - 1, 'Trigger event mask'))
    action(event)
    relation = native['relation']
    if relation is not None:
        identifier(relation)
    if (relation is not None) != (event & MASK == 0):
        raise ValueError('Only DML triggers require a relation identity')
    engine, entrypoint = native['engine_name'], native['entrypoint']
    security = flag(native['sql_security'], 'Trigger SQL SECURITY', nullable=True)
    body = native['metadata_source']
    if engine is not None:
        identifier(engine)
        if entrypoint is not None:
            text(entrypoint, 'External trigger entrypoint')
        if body is not None:
            body = text(body, 'External trigger payload')
        if security is not None:
            raise ValueError('External triggers cannot declare SQL SECURITY')
    else:
        if entrypoint is not None:
            raise ValueError('External trigger entrypoint requires an engine')
        body = re.sub(r'^AS\b\s*', '', source(body, 'Trigger body'), count=1, flags=re.IGNORECASE)
        body = source(body, 'Trigger body')
    return {'relation': relation, 'trigger_type': event,
            'inactive': flag(native['inactive'], 'Trigger inactive state'),
            'position': int(integer(native['position'], 0, 32767, 'Trigger position')),
            'metadata_source': body, 'sql_security': security, 'engine_name': engine, 'entrypoint': entrypoint}


def context(after, current):
    if after['relation'] is not None and not any(
            row['kind'] in {'table', 'view'} and row['name'] == after['relation']
            for row in current['rows'].values()):
        raise ValueError('Trigger relation is unavailable in the observed catalog')
    return dependencies(current)


def statements(before, after):
    if before is not None:
        if before['relation'] != after['relation'] or (before['trigger_type'] & MASK) != (after['trigger_type'] & MASK):
            raise ValueError('Trigger relation or family change requires an explicit lifecycle plan')
        if after['trigger_type'] & MASK and before['trigger_type'] != after['trigger_type']:
            raise ValueError('Firebird ALTER cannot change database or DDL trigger events')
        if all(before[key] == after[key] for key in FIELDS - {'description'}):
            return []
    sql = ('CREATE' if before is None else 'ALTER') + ' TRIGGER ' + identifier(after['name'])
    if before is None and after['relation'] is not None:
        sql += ' FOR ' + identifier(after['relation'])
    sql += ' INACTIVE' if after['inactive'] == '1' else ' ACTIVE'
    if before is None or after['trigger_type'] & MASK == 0:
        sql += ' ' + action(after['trigger_type'])
    sql += ' POSITION ' + str(after['position'])
    if after['engine_name'] is not None:
        sql += '\nEXTERNAL'
        if after['entrypoint'] is not None:
            sql += ' NAME ' + literal(after['entrypoint'])
        sql += ' ENGINE ' + identifier(after['engine_name'])
        if after['metadata_source'] is not None:
            sql += '\nAS ' + literal(after['metadata_source'])
    else:
        if after['sql_security'] is not None:
            sql += '\nSQL SECURITY ' + ('DEFINER' if after['sql_security'] == '1' else 'INVOKER')
        elif before is not None and before['sql_security'] is not None:
            sql += '\nDROP SQL SECURITY'
        sql += '\nAS\n' + after['metadata_source']
    return [sql]
