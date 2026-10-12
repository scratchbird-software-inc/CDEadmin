"""Owner/target/dialect scoped SQL history in the application configuration DB.

Records describe host requests, never native transaction finality. No parameter
values, query results or connection credentials enter this repository.
"""
from dataclasses import dataclass
import json
import re
import time
import uuid

from sqlalchemy import select, func, delete
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

DEFAULT_POLICY = {'capture_source': False, 'retention_days': 30, 'max_records': 500}
SENSITIVE = re.compile(r'\b(?:PASSWORD|SECRET|TOKEN)\b', re.IGNORECASE)
POSTGRESQL_CREDENTIAL_URI = re.compile(r'\bpostgres(?:ql)?://[^\s/]*@', re.IGNORECASE)
MYSQL_CREDENTIAL_URI = re.compile(r'\bmysql(?:x)?://[^\s/]*@', re.IGNORECASE)
MYSQL_AUTHENTICATION = re.compile(r'\bIDENTIFIED\s+(?:BY|WITH)\b', re.IGNORECASE)


class HistoryError(ValueError):
    pass


@dataclass(frozen=True)
class HistoryScope:
    owner: int
    server: int
    target: str
    dialect: int | str
    engine: str = 'firebird'

    @property
    def key(self):
        return 'scratchrobin:' + self.engine + '-history:v1:' + json.dumps([self.target, self.dialect], separators=(',', ':'))


def policy(value):
    if not isinstance(value, dict) or set(value) != set(DEFAULT_POLICY):
        raise HistoryError('History policy requires source capture, retention days and record limit')
    if type(value['capture_source']) is not bool:
        raise HistoryError('Source capture must be boolean')
    for key, maximum in [('retention_days', 365), ('max_records', 1000)]:
        if type(value[key]) is not int or not 1 <= value[key] <= maximum:
            raise HistoryError(f'{key} must be between 1 and {maximum}')
    return dict(value)


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def decode(value):
    return json.loads(value.decode('utf-8') if isinstance(value, bytes) else value)


class QueryHistory:
    def __init__(self, engine, model, clock=time.time):
        self.engine, self.model, self.clock = engine, model, clock

    def _filters(self, scope):
        return (self.model.uid == scope.owner, self.model.sid == scope.server,
                self.model.dbname == scope.key)

    def _run(self, scope, callback):
        if (type(scope.owner) is not int or type(scope.server) is not int or
                scope.owner < 1 or scope.server < 1 or not isinstance(scope.target, str) or
                not 1 <= len(scope.target) <= 256 or not (
                    scope.engine == 'firebird' and type(scope.dialect) is int and scope.dialect in (1, 2, 3) or
                    scope.engine == 'postgresql' and scope.dialect == 'postgresql-sql' or
                    scope.engine == 'mysql' and scope.dialect == 'mysql-sql')):
            raise HistoryError('History requires an authorized owner, server, database target and SQL dialect')
        # A separate SQLAlchemy session must never commit unrelated application
        # work. Retry only configuration-store contention, never native SQL.
        for attempt in range(3):
            with Session(self.engine) as session:
                try:
                    result = callback(session)
                    session.commit()
                    return result
                except (IntegrityError, OperationalError) as error:
                    session.rollback()
                    if attempt == 2:
                        raise HistoryError('SQL history storage is unavailable (' + type(error).__name__ + ')') from None

    def _policy(self, session, scope):
        row = session.scalars(select(self.model).where(*self._filters(scope), self.model.srno == 0)).first()
        return policy(decode(row.query_info)['policy']) if row else dict(DEFAULT_POLICY)

    def _entries(self, session, scope, selected_policy):
        rows = list(session.scalars(select(self.model).where(*self._filters(scope), self.model.srno > 0)
                                    .order_by(self.model.srno.desc())))
        admitted = []
        cutoff = self.clock() - selected_policy['retention_days'] * 86400
        for row in rows:
            entry = decode(row.query_info)
            if entry['created_at'] < cutoff or len(admitted) >= selected_policy['max_records']:
                session.delete(row)
            else:
                admitted.append((row, entry))
        return admitted

    def configure(self, scope, values):
        selected = policy(values)
        def save(session):
            row = session.scalars(select(self.model).where(*self._filters(scope), self.model.srno == 0)).first()
            if row is None:
                row = self.model(uid=scope.owner, sid=scope.server, dbname=scope.key, srno=0,
                                 last_updated_flag='N', query_info=encode({'policy': selected}))
                session.add(row)
            else:
                row.query_info = encode({'policy': selected})
            self._entries(session, scope, selected)
            return selected
        return self._run(scope, save)

    def read(self, scope, search=''):
        if not isinstance(search, str) or len(search) > 512:
            raise HistoryError('History search must be text of at most 512 characters')
        def load(session):
            selected = self._policy(session, scope)
            entries = [entry for _row, entry in self._entries(session, scope, selected)]
            return {'policy': selected, 'total_retained': len(entries),
                    'entries': [entry for entry in entries if search.casefold() in (entry.get('source') or '').casefold()],
                    'scope': {'database_target_id': scope.target, **(
                        {'engine_id': scope.engine, 'language_profile': scope.dialect} if scope.engine in {'postgresql', 'mysql'}
                        else {'client_sql_dialect': scope.dialect})}}
        return self._run(scope, load)

    def clear(self, scope):
        def remove(session):
            count = session.execute(delete(self.model).where(*self._filters(scope), self.model.srno > 0)).rowcount
            return {'removed': count}
        return self._run(scope, remove)

    def record(self, scope, source, *, sensitive=False, kind='statement'):
        if not isinstance(source, str) or type(sensitive) is not bool or kind not in ('statement', 'script', 'script-prepared'):
            raise HistoryError('Invalid SQL history request')
        identity = str(uuid.uuid4())
        def save(session):
            selected = self._policy(session, scope)
            entries = self._entries(session, scope, selected)
            if not selected['capture_source']:
                return {'recorded': False, 'reason': 'Source capture disabled'}
            if (sensitive or SENSITIVE.search(source) or
                    (scope.engine == 'postgresql' and POSTGRESQL_CREDENTIAL_URI.search(source)) or
                    (scope.engine == 'mysql' and (
                        MYSQL_CREDENTIAL_URI.search(source) or MYSQL_AUTHENTICATION.search(source)))):
                reason = 'Sensitive source omitted'
            elif len(source.encode('utf-8')) > 65536:
                reason = 'Source exceeds 64 KiB'
            else:
                reason = None
            # The stable event ID also makes configuration-store retries safe
            # if a commit reply was lost. It is not a native execution token.
            if any(entry['entry_id'] == identity for _row, entry in entries):
                return {'recorded': True, 'entry_id': identity}
            latest = session.scalar(select(func.max(self.model.srno)).where(*self._filters(scope))) or 0
            if latest >= 2147483646:
                raise HistoryError('History sequence exhausted; clear this history scope')
            entry = {'entry_id': identity, 'created_at': self.clock(),
                     'source': None if reason else source, 'source_omitted_reason': reason,
                     'request_state': 'submitted', 'kind': kind}
            session.add(self.model(uid=scope.owner, sid=scope.server, dbname=scope.key, srno=latest + 1,
                                   query_info=encode(entry), last_updated_flag='N'))
            session.flush()
            self._entries(session, scope, selected)
            return {'recorded': True, 'entry_id': identity, 'source_omitted_reason': reason}
        return self._run(scope, save)

    def observation(self, scope, entry_id, state):
        if state not in ('accepted', 'request-error', 'prepared', 'preparation-rejected'):
            raise HistoryError('History state is a host request observation')
        def update(session):
            for row, entry in self._entries(session, scope, self._policy(session, scope)):
                if entry['entry_id'] == entry_id:
                    entry['request_state'] = state
                    row.query_info = encode(entry)
                    return True
            return False
        return self._run(scope, update)


def repository():
    from pgadmin.model import QueryHistoryModel, db
    return QueryHistory(db.engine, QueryHistoryModel)
