"""Private process-local search jobs; no persisted values or SQL history."""
from copy import deepcopy
from decimal import Decimal
import threading
import time
import uuid

from ..providers.mysql_family import mysql_content_search as native
from ..providers.mysql_family.mysql_catalog import DENIED, identifier
from ..providers.mysql_family.mysql_clone import thread_matches


def public_error(error):
    return {'error_type': type(error).__name__, 'error_code': getattr(error, 'errno', None),
            'sqlstate': getattr(error, 'sqlstate', None)}


class SearchJob:
    def __init__(self, scope, observer, control, schema, tables, selected, authorize):
        self.id, self.scope, self.observer, self.control = str(uuid.uuid4()), scope, observer, control
        self.schema, self.tables, self.selected, self.authorize = schema, tables, selected, authorize
        self.lock, self.cancelled = threading.RLock(), threading.Event()
        self.created, self.finished, self.closed = time.monotonic(), None, False
        self.state, self.coverage, self.matches, self.locators = 'running', [], [], {}
        self.failed = False
        self.deadline_reached = False
        self.cancellation = {'requested': False, 'native_kill_sent': False}
        self.identity = deepcopy(observer.identity)
        self.worker = threading.Thread(target=self.run, daemon=True, name='mysql-private-content-search')
        self.timer = threading.Timer(selected['seconds'], lambda: self.stop('deadline'))
        self.timer.daemon = True

    def change(self, target, **values):
        with self.lock: target.update(values)

    def snapshot(self):
        with self.lock:
            return {'job_id': self.id, 'state': self.state, 'terminal': self.finished is not None,
                'schema_name': self.schema, 'identity': {k: native.display(v) for k,v in self.identity.items()},
                'coverage': deepcopy(self.coverage), 'matches': deepcopy(self.matches),
                'selected_tables': len(self.tables), 'cancellation': dict(self.cancellation),
                'bounds': {k: self.selected[k] for k in ('limit','seconds','indexed_only','mode')},
                'elapsed_seconds': round((self.finished or time.monotonic())-self.created, 3),
                'retention': 'private process memory; expires after five minutes; no SQL/history persistence',
                'consistency': 'Independent read-only transaction per table; engine-native visibility, no database-wide snapshot',
                'identity_basis': 'Exact native server UUID, table/column names and structural fingerprint; rows can subsequently change'}

    def stop(self, reason='user'):
        # Pin the owned connection until the identity check and KILL return.
        # The worker cannot close/release it and permit connection-ID reuse.
        with self.lock:
            if self.cancelled.is_set() or self.closed:
                return
            self.cancelled.set(); self.cancellation.update(requested=True,reason=reason)
            self.deadline_reached = reason=='deadline'
            try:
                identity = {'connection_id': str(self.identity['connection_id']),
                    'thread_id': str(self.identity['thread_id']) if self.identity['thread_id'] else None}
                current = self.control.query('SELECT @@server_uuid AS server_uuid')[0]
                if current['server_uuid'] == self.identity['server_uuid'] and thread_matches(self.control.connection, identity):
                    self.control.query('KILL QUERY '+identity['connection_id'])
                    self.cancellation['native_kill_sent'] = True
                else:
                    self.cancellation['identity'] = 'native-thread-unconfirmed; wait for bounded observer completion'
            except Exception as error:
                self.cancellation.update(public_error(error))

    def interrupted(self):
        return self.failed or self.cancelled.is_set() or time.monotonic()-self.created >= self.selected['seconds']

    def run(self):
        try:
            for item in self.tables:
                table = item['table_name']
                observed = {'table_name': table, 'columns': [], 'state': 'unsearched'}
                with self.lock: self.coverage.append(observed)
                if self.interrupted() or len(self.matches)>=self.selected['limit']:
                    self.change(observed, reason='cancelled' if self.cancelled.is_set() else 'search-bound-reached')
                    continue
                try:
                    self.authorize()
                    self.observer.begin()
                    # A native table MDL is retained until this table's read-only
                    # transaction ends. Metadata is re-read under that lock.
                    first = identifier(item['columns'][0])
                    qualified = identifier(self.schema)+'.'+identifier(table)
                    self.observer.query('SELECT '+first+' FROM '+qualified+' WHERE 0', limit=1)
                    source = native.describe(self.observer, self.schema, table)
                    if source['fingerprint'] != item['fingerprint']:
                        raise native.SearchError('Native table structure changed; discover and select it again')
                    by_name = {c['COLUMN_NAME']: c for c in source['columns']}
                    if any(n not in by_name for n in item['columns']):
                        raise native.SearchError('A selected native column is unavailable')
                    self.change(observed, state='observed', source_fingerprint=source['fingerprint'],
                        engine=source['engine'], snapshot='native transaction; nontransactional engines have no snapshot guarantee',
                        row_navigation='native unique key' if source['key'] else 'unavailable: no fully readable nonnullable native unique key')
                    for column_name in item['columns']:
                        report = {'column_name': column_name, 'state': 'unsearched'}
                        with self.lock: observed['columns'].append(report)
                        if self.interrupted() or len(self.matches)>=self.selected['limit']:
                            self.change(report, reason='cancelled' if self.cancelled.is_set() else 'search-bound-reached'); continue
                        self.authorize()
                        column = by_name[column_name]
                        predicate = native.predicate(column, self.selected)
                        if predicate is None:
                            self.change(report, reason='type-or-exact-value-not-applicable'); continue
                        try:
                            remaining = self.selected['limit']-len(self.matches)
                            keys = []
                            for index, key in enumerate(source['key']):
                                expression = identifier(key)
                                if by_name[key]['DATA_TYPE'] in native.TEMPORAL:
                                    expression = 'CAST('+expression+' AS CHAR)'
                                keys.append(expression+' AS sr_key_'+str(index))
                            projection = (['NULL AS sr_preview','NULL AS sr_value_bytes'] if self.selected['mode']=='is_null' else
                                [native.preview(column)+' AS sr_preview','OCTET_LENGTH('+identifier(column_name)+') AS sr_value_bytes'])+keys
                            sql = 'SELECT /*+ MAX_EXECUTION_TIME(3000) */ '+','.join(projection)+' FROM '+qualified
                            if self.selected['indexed_only']:
                                candidates = [p for p in source['indexes'] if p['SEQ_IN_INDEX']==1 and
                                    p['COLUMN_NAME']==column_name and p['IS_VISIBLE']=='YES']
                                if candidates:
                                    sql += ' FORCE INDEX ('+identifier(candidates[0]['INDEX_NAME'])+')'
                            sql += ' WHERE '+predicate[0]+' LIMIT '+str(remaining+1)
                            if self.selected['indexed_only'] and not native.indexed_plan(self.observer, sql, predicate[1]):
                                self.change(report, reason='native-plan-has-no-key-lookup-or-range'); continue
                            rows = self.observer.query(sql, predicate[1], limit=remaining+1)
                            if self.observer.warning_count:
                                warnings = self.observer.query('SHOW WARNINGS LIMIT 20', limit=20)
                                with self.lock:
                                    report.update(state='unsearched', reason='native-comparison-or-preview-warning',
                                        warning_codes=[r['Code'] for r in warnings])
                                continue
                            self.change(report, state='searched', returned=min(len(rows),remaining), truncated=len(rows)>remaining,
                                comparison='native column collation / numeric comparison / binary bytes',
                                data_type=column['COLUMN_TYPE'], collation=column['COLLATION_NAME'])
                            for row in rows[:remaining]:
                                match_id = str(uuid.uuid4())
                                match = {'match_id': match_id, 'table_name': table, 'column_name': column_name,
                                    'preview': native.display(row['sr_preview']), 'value_bytes': native.display(row['sr_value_bytes']),
                                    'preview_limit': 256, 'preview_encoding': 'hex' if column['DATA_TYPE'] in native.BINARY else 'native text',
                                    'navigation_available': bool(source['key']), 'source_fingerprint': source['fingerprint']}
                                with self.lock:
                                    self.matches.append(match)
                                    if source['key']:
                                        self.locators[match_id] = {'source': {k:source[k] for k in ('schema_name','table_name','fingerprint','key')},
                                            'keys': [row['sr_key_'+str(i)] for i in range(len(source['key']))],
                                            'column_name': column_name, 'preview': row['sr_preview'], 'value_bytes': row['sr_value_bytes']}
                        except Exception as error:
                            self.change(report, **public_error(error), state='denied' if getattr(error,'errno',None) in DENIED else
                                'cancelled' if self.cancelled.is_set() else 'timed-out' if getattr(error,'errno',None) in {1205,3024} else 'failed')
                            if getattr(error,'errno',None) in {2006,2013,2055}:
                                raise
                except Exception as error:
                    self.change(observed, **public_error(error), state='denied' if getattr(error,'errno',None) in DENIED else 'unsearched')
                    if getattr(error,'errno',None) in {2006,2013,2055}: self.failed = True
                    if isinstance(error, native.SearchError): self.change(observed, reason=str(error))
                finally:
                    try: self.observer.rollback()
                    except Exception:
                        self.failed = True
            complete = all(t['state']=='observed' and all(c['state']=='searched' for c in t['columns']) for t in self.coverage)
            self.state = 'failed' if self.failed else 'bounded' if self.deadline_reached else 'cancelled' if self.cancelled.is_set() else 'bounded' if self.interrupted() or len(self.matches)>=self.selected['limit'] else 'completed' if complete else 'partial'
        except Exception as error:
            self.state = 'failed'
            with self.lock: self.coverage.append({'state':'failed', **public_error(error)})
        finally:
            with self.lock:
                self.closed = True
                self.timer.cancel()
                try: self.observer.close()
                finally:
                    try: self.control.close()
                    finally: self.finished = time.monotonic()


class SearchJobs:
    def __init__(self):
        self.lock, self.jobs = threading.RLock(), {}
        self.stopped = threading.Event()
        self.reaper = threading.Thread(target=self.expire,daemon=True,name='mysql-private-search-expiry')
        self.reaper.start()

    def prune(self):
        with self.lock:
            for key,job in list(self.jobs.items()):
                if job.finished and time.monotonic()-job.created>300:
                    with job.lock:
                        job.matches.clear();job.locators.clear();job.selected['value']=None
                    del self.jobs[key]

    def expire(self):
        while not self.stopped.wait(15):self.prune()

    def start(self, scope, observer, control, schema, tables, selected, authorize):
        with self.lock:
            self.prune()
            if len(self.jobs)>=64 or sum(j.scope[0]==scope[0] for j in self.jobs.values())>=8:
                raise native.SearchError('Clear a previous private search before starting another')
            job = SearchJob(scope, observer, control, schema, tables, selected, authorize)
            self.jobs[job.id] = job
            job.worker.start()
            job.timer.start()
            return job.snapshot()

    def get(self, scope, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None or job.scope != scope or time.monotonic()-job.created>300:
                raise native.SearchError('This owner-scoped private search expired or is unavailable')
            return job

    def forget(self, scope, job_id):
        job = self.get(scope, job_id)
        job.stop()
        if not job.closed:
            raise native.SearchError('Wait for cancellation to finish before clearing private results')
        with self.lock:
            self.jobs.pop(job_id, None)
            with job.lock:
                job.matches.clear();job.locators.clear();job.selected['value']=None
        return {'state':'cleared'}

    def close(self):
        self.stopped.set()
        with self.lock: jobs = list(self.jobs.values())
        for job in jobs: job.stop()
        for job in jobs: job.worker.join(timeout=12)


def navigate(observer, job, match_id):
    with job.lock:
        locator = job.locators.get(match_id)
        if locator is None:
            raise native.SearchError('No native unique-key locator is available for this match')
        locator = deepcopy(locator)
    if any(observer.identity[k]!=job.identity[k] for k in ('server_uuid','account','active_role')):
        raise native.SearchError('Row navigation reached another native server, account or role')
    source = locator['source']
    schema, table = source['schema_name'], source['table_name']
    qualified = identifier(schema)+'.'+identifier(table)
    try:
        observer.begin()
        observer.query('SELECT '+identifier(locator['column_name'])+' FROM '+qualified+' WHERE 0', limit=1)
        current = native.describe(observer, schema, table)
        if current['fingerprint']!=source['fingerprint'] or current['key']!=source['key']:
            raise native.SearchError('The native source structure changed; search again before navigating')
        # Reopen current row values. This is a fresh native read, never a claim
        # that an earlier observation is an immutable historical row version.
        readable = [c for c in current['columns'] if 'select' in c['PRIVILEGES'].split(',')]
        visible = readable[:100]
        matched = next(c for c in readable if c['COLUMN_NAME']==locator['column_name'])
        if matched not in visible:visible = visible[:99]+[matched]
        projection = [native.preview(c)+' AS '+identifier('v'+str(i)) for i,c in enumerate(visible)]
        clauses, parameters = [], []
        for key, value in zip(current['key'], locator['keys']):
            binary = isinstance(value, (bytes, bytearray, memoryview))
            expression, parameter = native.decimal_parameter(value) if isinstance(value, Decimal) else (
                ('UNHEX(%s)', bytes(value).hex()) if binary else ('%s', value))
            clauses.append(identifier(key)+' <=> '+expression)
            parameters.append(parameter)
        rows = observer.query('SELECT /*+ MAX_EXECUTION_TIME(3000) */ '+','.join(projection)+' FROM '+qualified+
            ' WHERE '+' AND '.join(clauses)+' LIMIT 2', tuple(parameters), limit=2)
        if observer.warning_count:
            raise native.SearchError('Native row navigation returned a conversion warning; the row is unconfirmed')
        if len(rows)>1:
            raise native.SearchError('The native key no longer identifies one row')
        values = [] if not rows else [{'column_name': c['COLUMN_NAME'], 'data_type': c['COLUMN_TYPE'],
            'preview': native.display(rows[0]['v'+str(i)]), 'preview_limit':256} for i,c in enumerate(visible)]
        return {'state': 'current-row' if rows else 'row-no-longer-visible', 'schema_name':schema, 'table_name':table,
            'values':values,'column_limit':100,'omitted_columns':len(readable)-len(visible),'source_fingerprint':current['fingerprint'],
            'basis':'Fresh native unique-key read; current values may differ from the search observation'}
    finally:
        observer.rollback()
