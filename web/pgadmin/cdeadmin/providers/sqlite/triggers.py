"""SQLite trigger target and WHEN compilation; native execution owns binding."""
import re
from pgadmin.cdeadmin.sdk import RelationalClientError
from .expressions import expression


def create(adapter, name, draft, options):
    timing = options.get('timing', 'BEFORE')
    events = options.get('events', ['INSERT'])
    if timing not in {'BEFORE','AFTER','INSTEAD OF'}:
        raise RelationalClientError('Invalid SQLite trigger timing')
    if not isinstance(events,list) or len(events)!=1 or events[0] not in {'INSERT','UPDATE','DELETE'}:
        raise RelationalClientError('SQLite trigger requires one INSERT, UPDATE or DELETE event')
    if options.get('active',True) is not True or options.get('position',0)!=0:
        raise RelationalClientError('SQLite has no inactive triggers or trigger position')
    table = adapter._qualified(adapter._option_path(options,'table'))
    body = adapter._safe_definition(draft.get('definition'))
    if not body:
        raise RelationalClientError('SQLite trigger requires a body')
    when = options.get('when')
    condition = ' WHEN (' + expression(when) + ')' if when else ''
    if not re.match(r'(?is)^BEGIN\b',body.strip()):
        body = 'BEGIN\n' + body.strip().rstrip(';') + ';\nEND'
    return f'CREATE TRIGGER {name} {timing} {events[0]} ON {table}{condition}\n{body}'
