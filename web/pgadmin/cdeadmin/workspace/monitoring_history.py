"""ScratchBird monitoring archive. No source credentials or interactive queries.

Each operation owns a destination transaction. A failed commit is unconfirmed;
callers must not replay it. Schema creation is an explicit operator operation.
"""
import hashlib
import json
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


class HistoryUnavailable(RuntimeError):
    def __init__(self, phase):
        super().__init__('Monitoring history operation unconfirmed')
        self.phase = phase


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('History timestamps require a timezone')
    return int(parsed.timestamp() * 1000000)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


# Only passive collector output enters the archive. Explicit detail requests,
# SQL inspection, credentials, context variables and native logs never do.
_FIELDS = {'schema', 'sample_id', 'scope', 'started_at', 'ended_at', 'status',
           'source_epoch', 'coverage', 'collector', 'groups', 'rates', 'derived', 'findings',
           'history_ingestion_gap', 'duration_seconds', 'transaction_refresh', 'service_probe', 'error_type'}
_DENIED = ('password', 'secret', 'token', 'credential', 'sql_text', 'query_text',
           'context_variable', 'server_log', 'connection_string', 'dsn')


def sanitized(sample, engine=None):
    def clean(value, depth=0):
        if depth > 24:
            raise ValueError('History sample exceeds nesting limit')
        if isinstance(value, dict):
            return {key: clean(item, depth + 1) for key, item in value.items()
                    if isinstance(key, str) and not any(word in key.lower() for word in _DENIED)}
        if isinstance(value, list):
            return [clean(item, depth + 1) for item in value]
        if value is None or isinstance(value, (str, bool, int, float)):
            return value
        raise ValueError('Unsupported monitoring value')
    result = clean({key: value for key, value in sample.items() if key in _FIELDS})
    if engine in {'mysql', 'mariadb'}:
        # The account and collector connection are deliberately not archived.
        result['identity'] = {key: sample.get('identity', {}).get(key)
                              for key in ('server_uid' if engine == 'mariadb' else 'server_uuid', 'database_name', 'version')}
        result['transaction_completed'] = sample.get('transaction_completed') is True
        result['elapsed_ms'] = sample.get('elapsed_ms')
    elif engine == 'postgresql':
        result['identity'] = {key: sample.get('identity', {}).get(key) for key in (
            'database', 'database_oid', 'postmaster_started_at', 'in_recovery',
            'statistics_visibility')}
        result['transaction_completed'] = sample.get('transaction_completed') is True
    elif engine in {'duckdb', 'sqlite'}:
        result['identity'] = {key: sample.get('identity', {}).get(key) for key in (
            'database_name', 'version', 'target_id', 'engine_id')}
    if len(encoded(result).encode()) > 2 * 1024 * 1024:
        raise ValueError('History sample exceeds size limit')
    return result


def measures(sample):
    """Exact numeric scalar summaries; counts are never treated as deltas."""
    result = {}
    def walk(value, path):
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, path + [key])
        elif isinstance(value, list):
            for row in value:
                if not isinstance(row, dict):
                    continue
                # Stable native row identity, never a row's transient position.
                key = next((row[name] for name in ('variable_name', 'engine', 'processlist_id', 'channel_name',
                             'name', 'datid', 'relid', 'pid', 'database_name')
                             if isinstance(row.get(name), (str, int)) and not isinstance(row.get(name), bool)), None)
                if key is not None:
                    walk(row, path + [encoded(key)])
                elif len(value) == 1:
                    # Embedded scalar groups have one row and no native row key.
                    walk(row, path + ['scalar'])
        elif isinstance(value, (str, int)) and not isinstance(value, bool):
            try:
                number = Decimal(value)
                if number.is_finite() and len(str(value)) <= 128:
                    result['/'.join(path)] = str(number)
            except InvalidOperation:
                pass
    for key in ('groups', 'rates', 'derived'):
        walk(sample.get(key, {}), [key])
    return result


class MonitoringHistory:
    def __init__(self, connect, *, namespace, raw_days=7, rollup_days=90,
                 bucket_seconds=300, clock=time.time):
        if not isinstance(namespace, str) or not 1 <= len(namespace) <= 128:
            raise ValueError('History namespace is required')
        if (type(raw_days) is not int or type(rollup_days) is not int or
                not 1 <= raw_days <= rollup_days <= 3660 or
                type(bucket_seconds) is not int or not 60 <= bucket_seconds <= 86400):
            raise ValueError('Invalid history retention')
        self.connect, self.namespace, self.clock = connect, namespace, clock
        self.raw_days, self.rollup_days = raw_days, rollup_days
        self.bucket_us = bucket_seconds * 1000000
        self.lock = threading.RLock()
        self._maintained = 0

    @contextmanager
    def transaction(self):
        connection = None
        phase = 'connect'
        try:
            connection = self.connect()
            cursor = connection.cursor()
            phase = 'execute'
            yield cursor
            phase = 'commit'
            connection.commit()
        except Exception as error:
            if connection is not None:
                try:
                    connection.rollback()
                except Exception:
                    pass
            if isinstance(error, (ValueError, PermissionError)):
                raise
            raise HistoryUnavailable(phase) from None
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass

    def initialize(self):
        """Run once on a dedicated destination database, before enabling writers."""
        with self.lock, self.transaction() as cur:
            cur.execute('CREATE TABLE cde_monitor_history ('
                        'record_id VARCHAR(64) PRIMARY KEY, namespace VARCHAR(128) NOT NULL, '
                        'scope_id VARCHAR(64) NOT NULL, tier VARCHAR(8) NOT NULL, '
                        'observed_us BIGINT NOT NULL, ingested_us BIGINT NOT NULL, payload TEXT NOT NULL)')
            cur.execute('CREATE TABLE cde_monitor_history_version (version INTEGER NOT NULL)')
            cur.execute('INSERT INTO cde_monitor_history_version (version) VALUES (1)')
            cur.execute('CREATE INDEX cde_monitor_history_scope ON cde_monitor_history '
                        '(namespace, scope_id, tier, observed_us)')

    @staticmethod
    def _check_schema(cur):
        cur.execute('SELECT version FROM cde_monitor_history_version')
        if cur.fetchall() != [(1,)]:
            raise RuntimeError('Unsupported monitoring archive schema')

    def scope(self, policy, engine):
        return hashlib.sha256(encoded([self.namespace, policy.owner_id, engine,
                                      policy.endpoint_id, policy.target_id]).encode()).hexdigest()

    def write(self, policy, engine, revision, route_revision, sample):
        sample = sanitized(sample, engine)
        observed = timestamp(sample['ended_at'])
        now = int(self.clock() * 1000000)
        if observed > now + 300000000:
            raise ValueError('Observation is in the future')
        scope = self.scope(policy, engine)
        identity = hashlib.sha256(encoded([scope, sample['sample_id']]).encode()).hexdigest()
        metadata = {}
        if engine == 'firebird':
            from ..providers.firebird.monitoring_inventory import METADATA
            metadata = {name: {key: value for key, value in group.items()
                              if key not in ('age_seconds', 'observed_at')}
                        for name, group in sample.get('groups', {}).items()
                        if name in set(METADATA) | {'page_inventory', 'crypt_identity'}}
        elif engine in {'mysql', 'mariadb'}:
            metadata = {name: {key: value for key, value in group.items()
                              if key not in {'observed_at', 'observation_age_seconds'}}
                        for name, group in sample.get('groups', {}).items()
                        if name in {'settings', 'storage'}}
        elif engine in {'postgresql', 'duckdb', 'sqlite'}:
            names = {'settings'} if engine == 'postgresql' else {'database', 'extensions'}
            metadata = {name: {key: value for key, value in group.items()
                              if key not in {'observed_at', 'observation_age_seconds'}}
                        for name, group in sample.get('groups', {}).items()
                        if name in names}
        provenance = {'metadata_revision': hashlib.sha256(encoded(metadata).encode()).hexdigest(),
                      'collection_interval_seconds': policy.interval_seconds,
                      'metadata_interval_seconds': policy.metadata_interval_seconds,
                      'native_metric_sources': list(policy.native_metric_sources),
                      'schema_version': 1, 'engine': engine, 'owner_id': policy.owner_id,
                      'endpoint_id': policy.endpoint_id, 'target_id': policy.target_id,
                      'namespace': self.namespace, 'policy_revision': revision,
                      'coverage_revision': hashlib.sha256(encoded([sample.get('schema'), sample.get('coverage')]).encode()).hexdigest(),
                      'route_revision': route_revision, 'observed_us': observed,
                      'ingested_us': now, 'sample': sample}
        bucket = observed // self.bucket_us * self.bucket_us
        roll_id = hashlib.sha256(encoded([scope, revision, route_revision, bucket,
                     sample.get('source_epoch'), sample.get('rates', {}).get('epoch'),
                     provenance['metadata_revision'], sample.get('coverage'), sample['status']]).encode()).hexdigest()
        with self.lock, self.transaction() as cur:
            self._check_schema(cur)
            cur.execute('SELECT payload FROM cde_monitor_history WHERE record_id=:id', {'id': identity})
            previous = cur.fetchone()
            if previous:
                old = json.loads(previous[0])
                if old['sample'] != sample or old['policy_revision'] != revision or old['route_revision'] != route_revision:
                    raise ValueError('Observation identity collision')
                return
            self._insert(cur, identity, scope, 'raw', observed, now, provenance)
            cur.execute('SELECT payload FROM cde_monitor_history WHERE record_id=:id', {'id': roll_id})
            previous = cur.fetchone()
            summary = json.loads(previous[0]) if previous else {
                **provenance, 'aggregation': {'count': 0, 'first_us': observed,
                    'last_us': observed, 'bucket_us': bucket, 'measures': {}}}
            agg = summary['aggregation']
            agg['count'] += 1
            agg['first_us'] = min(agg['first_us'], observed)
            if observed >= agg['last_us']:
                summary.update(provenance)
            agg['last_us'] = max(agg['last_us'], observed)
            for path, value in measures(sample).items():
                item = agg['measures'].setdefault(path, {'count': 0, 'min': value, 'max': value})
                item['count'] += 1
                item['min'] = str(min(Decimal(item['min']), Decimal(value)))
                item['max'] = str(max(Decimal(item['max']), Decimal(value)))
            if len(encoded(summary).encode()) > 4 * 1024 * 1024:
                raise ValueError('History aggregate exceeds size limit')
            if previous:
                cur.execute('UPDATE cde_monitor_history SET payload=:payload, observed_us=:observed, '
                            'ingested_us=:now WHERE record_id=:id',
                            {'payload': encoded(summary), 'observed': agg['last_us'], 'now': now, 'id': roll_id})
            else:
                self._insert(cur, roll_id, scope, 'rollup', observed, now, summary)
            if self.clock() - self._maintained >= 60:
                self._prune(cur, now)
                self._maintained = self.clock()

    def _insert(self, cur, identity, scope, tier, observed, now, payload):
        cur.execute('INSERT INTO cde_monitor_history '
                    '(record_id,namespace,scope_id,tier,observed_us,ingested_us,payload) '
                    'VALUES (:id,:namespace,:scope,:tier,:observed,:now,:payload)',
                    {'id': identity, 'namespace': self.namespace, 'scope': scope,
                     'tier': tier, 'observed': observed, 'now': now, 'payload': encoded(payload)})

    def _prune(self, cur, now):
        for tier, days in (('raw', self.raw_days), ('rollup', self.rollup_days)):
            cur.execute('DELETE FROM cde_monitor_history WHERE namespace=:namespace '
                        'AND tier=:tier AND observed_us<:cutoff',
                        {'namespace': self.namespace, 'tier': tier, 'cutoff': now-days*86400000000})

    def maintain(self):
        with self.lock, self.transaction() as cur:
            self._check_schema(cur)
            self._prune(cur, int(self.clock()*1000000))

    def query(self, policy, engine, *, start, end, tier='raw', limit=120, after=None):
        start, end = timestamp(start), timestamp(end)
        if tier not in ('raw', 'rollup') or type(limit) is not int or not 1 <= limit <= 720:
            raise ValueError('Invalid history resolution or limit')
        if start >= end or end-start > self.rollup_days*86400000000:
            raise ValueError('Invalid history window')
        cutoff = int(self.clock()*1000000)-(self.raw_days if tier == 'raw' else self.rollup_days)*86400000000
        params = {'namespace': self.namespace, 'scope': self.scope(policy, engine),
                  'tier': tier, 'start': max(start, cutoff), 'end': end, 'limit': min(limit, 32)+1}
        page = ''
        if after is not None:
            if not isinstance(after, str) or len(after) > 100:
                raise ValueError('Invalid history cursor')
            position, identity = after.split(':', 1)
            if len(identity) != 64 or any(c not in '0123456789abcdef' for c in identity):
                raise ValueError('Invalid history cursor')
            params.update(position=int(position), identity=identity)
            page = ' AND (observed_us>:position OR (observed_us=:position AND record_id>:identity))'
        with self.transaction() as cur:
            self._check_schema(cur)
            cur.execute('SELECT record_id, observed_us, payload FROM cde_monitor_history '
                        'WHERE namespace=:namespace AND scope_id=:scope AND tier=:tier '
                        'AND observed_us>=:start AND observed_us<:end' + page +
                        ' ORDER BY observed_us, record_id LIMIT :limit', params)
            rows = cur.fetchall()
        page_limit = min(limit, 32)
        more = len(rows) > page_limit
        bounded, used = [], 0
        for row in rows[:page_limit]:
            size = len(row[2].encode())
            if bounded and used + size > 8 * 1024 * 1024:
                more = True
                break
            bounded.append(row)
            used += size
        rows = bounded
        samples = []
        for _, observed, payload in rows:
            item = json.loads(payload)
            sample = item.pop('sample')
            sample['runtime_elapsed_seconds'] = (observed-start)/1000000
            sample['history_provenance'] = item
            # Rollup representative rates cannot imply continuous raw coverage.
            if tier == 'rollup':
                sample['rates'] = {'status': 'gap', 'reason': 'downsampled-window'}
            samples.append(sample)
        return {'history': 'scratchbird', 'state': 'historical', 'samples': samples,
                'tier': tier, 'start_us': start, 'end_us': end, 'retention_cutoff_us': cutoff,
                'bucket_seconds': self.bucket_us//1000000,
                'next': (str(rows[-1][1])+':'+rows[-1][0]) if more else None}


def configured_history(app):
    """Trusted server config only; never accept destination secrets from HTTP."""
    config = app.config.get('CDEADMIN_MONITORING_HISTORY')
    if not config or not config.get('enabled'):
        return None
    if not isinstance(config.get('connection'), dict) or any(
            key in config['connection'] for key in ('password', 'dsn')):
        raise ValueError('History connection requires environment credentials')
    if not isinstance(config.get('password_env'), str) or not config['password_env']:
        raise ValueError('History password environment is required')
    settings = dict(config['connection'])
    settings.setdefault('connect_timeout', 5)
    settings.setdefault('socket_timeout', 10)
    for key in ('connect_timeout', 'socket_timeout'):
        if type(settings[key]) is not int or not 1 <= settings[key] <= 30:
            raise ValueError('History destination timeout must be bounded')
    import os
    def connect():
        import scratchbird
        options = {**settings, 'password': os.environ[config['password_env']]}
        return scratchbird.connect(**options)
    return MonitoringHistory(connect, namespace=config['namespace'],
        **{key: config[key] for key in ('raw_days', 'rollup_days', 'bucket_seconds') if key in config})
