"""Bounded MySQL 9.7 workload observations. No SQL/session history writes."""
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import re
import time

RANKS = {'total_latency': 'SUM_TIMER_WAIT', 'mean_latency': 'AVG_TIMER_WAIT',
         'executions': 'COUNT_STAR', 'rows_examined': 'SUM_ROWS_EXAMINED',
         'temporary_tables': 'SUM_CREATED_TMP_TABLES',
         'disk_temporary_tables': 'SUM_CREATED_TMP_DISK_TABLES'}
DIGEST_FIELDS = ('SCHEMA_NAME,DIGEST,DIGEST_TEXT,COUNT_STAR,SUM_TIMER_WAIT,AVG_TIMER_WAIT,'
    'MAX_TIMER_WAIT,SUM_LOCK_TIME,SUM_ERRORS,SUM_WARNINGS,SUM_ROWS_SENT,SUM_ROWS_EXAMINED,'
    'SUM_CREATED_TMP_TABLES,SUM_CREATED_TMP_DISK_TABLES,SUM_SORT_ROWS,SUM_NO_INDEX_USED,'
    'FIRST_SEEN,LAST_SEEN,QUANTILE_95,QUANTILE_99')
CONSUMERS = ('global_instrumentation', 'thread_instrumentation', 'statements_digest',
             'events_statements_current', 'events_statements_history_long',
             'events_waits_current', 'events_waits_history_long')
MAX_LOG_BYTES = 1024 * 1024
MAX_LOG_ENTRIES = 500


class WorkloadError(ValueError):
    """Public, source-free admission failure."""


def schema_name(value):
    if value is not None and (not isinstance(value, str) or not value or len(value) > 64 or '\x00' in value):
        raise WorkloadError('Select an exact native schema name or server scope')
    return value


def selection(value):
    if (not isinstance(value, dict) or set(value) != {'schema_name', 'digest'} or
            not isinstance(value['digest'], str) or not re.fullmatch('[0-9a-fA-F]{64}', value['digest'])):
        raise WorkloadError('Select one native statement digest')
    return schema_name(value['schema_name']), value['digest']


def observe(reader, schema=None, rank='total_latency'):
    """reader has the monitor's bounded native reads and denied-group handling."""
    schema_name(schema)
    if rank not in RANKS:
        raise WorkloadError('Select a supported native workload ranking')
    result = {'groups': {}}
    where, params = (' WHERE SCHEMA_NAME=%s', (schema,)) if schema is not None else ('', None)
    reader._group(result, 'workload_digests', 'SELECT ' + DIGEST_FIELDS +
        ' FROM performance_schema.events_statements_summary_by_digest' + where +
        ' ORDER BY ' + RANKS[rank] + ' DESC, SCHEMA_NAME, DIGEST LIMIT 101', params,
        scope='database' if schema is not None else 'server')
    reader._group(result, 'workload_settings', 'SELECT @@performance_schema AS performance_schema,'
        '@@performance_schema_digests_size AS digests_size,@@max_digest_length AS max_digest_length,'
        '@@performance_schema_max_digest_length AS stored_digest_length,'
        '@@slow_query_log AS slow_query_log,@@log_output AS log_output,'
        '@@long_query_time AS long_query_time', scope='server')
    reader._group(result, 'workload_consumers', 'SELECT NAME,ENABLED FROM performance_schema.setup_consumers '
        'WHERE NAME IN (' + ','.join(['%s'] * len(CONSUMERS)) + ') ORDER BY NAME LIMIT 101', CONSUMERS, scope='server')
    reader._group(result, 'workload_instruments', "SELECT SUBSTRING_INDEX(NAME,'/',1) AS family,"
        "COUNT(*) AS instrument_count,CAST(SUM(ENABLED='YES') AS UNSIGNED) AS enabled_count,"
        "CAST(SUM(TIMED='YES') AS UNSIGNED) AS timed_count "
        "FROM performance_schema.setup_instruments WHERE NAME LIKE 'statement/%%' OR NAME LIKE 'wait/%%' "
        "GROUP BY family LIMIT 101", scope='server')
    reader._group(result, 'workload_epoch', 'SELECT VARIABLE_NAME,VARIABLE_VALUE FROM performance_schema.global_status '
        "WHERE VARIABLE_NAME IN ('Uptime','Performance_schema_digest_lost') ORDER BY VARIABLE_NAME LIMIT 101", scope='server')
    reader._group(result, 'workload_waits', 'SELECT EVENT_NAME,COUNT_STAR,SUM_TIMER_WAIT,AVG_TIMER_WAIT '
        'FROM performance_schema.events_waits_summary_global_by_event_name WHERE COUNT_STAR>0 '
        'ORDER BY SUM_TIMER_WAIT DESC,EVENT_NAME LIMIT 101', scope='server')
    index_where, index_params = (' AND OBJECT_SCHEMA=%s', (schema,)) if schema is not None else ('', None)
    reader._group(result, 'workload_indexes', 'SELECT OBJECT_SCHEMA,OBJECT_NAME,INDEX_NAME,COUNT_STAR,'
        'SUM_TIMER_WAIT,COUNT_READ,SUM_TIMER_READ,COUNT_WRITE,SUM_TIMER_WRITE '
        'FROM performance_schema.table_io_waits_summary_by_index_usage WHERE COUNT_STAR>0' + index_where +
        ' ORDER BY SUM_TIMER_WAIT DESC,OBJECT_SCHEMA,OBJECT_NAME,INDEX_NAME LIMIT 101', index_params,
        scope='database' if schema is not None else 'server')
    result.update(rank=rank, schema_name=schema, timer_unit='picoseconds',
        sql_text='native-normalized-digests-only; samples require explicit private access',
        attribution='waits are server-wide; index activity is native object/index scope, not digest attribution',
        reset={'basis': 'native FIRST_SEEN and observed counter decreases; no global reset timestamp',
               'undetected_reset_possible': True, 'rates': 'not inferred', 'window': 'cumulative native summaries'})
    return result


def reset_evidence(previous, current):
    """Report observable discontinuity; never invent a native global reset epoch."""
    group = current.get('groups', {}).get('workload_digests', {})
    if not previous or group.get('status') != 'available':
        return {'state': 'baseline-unavailable', 'undetected_reset_possible': True}
    before = previous.get('groups', {}).get('workload_digests', {})
    if before.get('status') != 'available' or previous.get('source_epoch') != current.get('source_epoch'):
        return {'state': 'baseline-unavailable', 'undetected_reset_possible': True}
    prior = {(r['schema_name'], r['digest']): r for r in before['rows']}
    changed = []
    for row in group['rows']:
        old = prior.get((row['schema_name'], row['digest']))
        if old is None:
            continue
        if row['first_seen'] != old['first_seen'] or any(
                int(row[k]) < int(old[k]) for k in ('count_star', 'sum_timer_wait', 'sum_rows_examined',
                    'sum_created_tmp_tables', 'sum_created_tmp_disk_tables')):
            changed.append({'schema_name': row['schema_name'], 'digest': row['digest']})
    return {'state': 'reset-observed' if changed else 'no-reset-observed',
            'digests': changed, 'undetected_reset_possible': True}


def private_sample(reader, selected):
    schema, digest = selection(selected)
    rows = reader._read('SELECT IF(OCTET_LENGTH(QUERY_SAMPLE_TEXT)<=65536,QUERY_SAMPLE_TEXT,NULL) AS QUERY_SAMPLE_TEXT,QUERY_SAMPLE_SEEN,FIRST_SEEN '
        'FROM performance_schema.events_statements_summary_by_digest WHERE SCHEMA_NAME <=> %s AND DIGEST=%s LIMIT 1',
        (schema, digest))
    if not rows or not isinstance(rows[0]['query_sample_text'], str) or not rows[0]['query_sample_text']:
        raise WorkloadError('A native SQL sample is unavailable for this digest')
    value = rows[0]
    if len(value['query_sample_text'].encode('utf8')) > 65536:
        raise WorkloadError('The native SQL sample exceeds the private inspection limit')
    return {**value, 'sample_sha256': hashlib.sha256(value['query_sample_text'].encode('utf8')).hexdigest(),
            'privacy': 'private SQL; volatile response only; never stored in monitoring or SQL history'}


def digest_waits(reader, selected):
    schema, digest = selection(selected)
    result = {'groups': {}}
    reader._group(result, 'direct_statement_waits', 'SELECT w.EVENT_NAME,COUNT(*) AS count_star,'
        'SUM(w.TIMER_WAIT) AS sum_timer_wait FROM performance_schema.events_waits_history_long w '
        'JOIN performance_schema.events_statements_history_long s ON s.THREAD_ID=w.THREAD_ID '
        "AND s.EVENT_ID=w.NESTING_EVENT_ID AND w.NESTING_EVENT_TYPE='STATEMENT' "
        'WHERE s.CURRENT_SCHEMA <=> %s AND s.DIGEST=%s GROUP BY w.EVENT_NAME '
        'ORDER BY sum_timer_wait DESC,w.EVENT_NAME LIMIT 101', (schema, digest), scope='recent-direct-statement-waits')
    result['coverage'] = ('Only directly nested waits still retained in both native history rings. '
        'Stage-nested, evicted, disabled or denied events are not attributed. Empty is not proof of no waits.')
    return result


def cutoff(value):
    try:
        if not isinstance(value, str) or len(value) > 40:
            raise ValueError()
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if date.tzinfo is None or date.utcoffset().total_seconds() != 0:
            raise ValueError()
        return date.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError):
        raise WorkloadError('Select explicit UTC start and end timestamps') from None


def slow_table(reader, options):
    if not isinstance(options, dict) or set(options) != {'schema_name', 'start_utc', 'end_utc'}:
        raise WorkloadError('Select a schema and bounded UTC slow-log window')
    schema = schema_name(options['schema_name'])
    start, end = cutoff(options['start_utc']), cutoff(options['end_utc'])
    if schema is None or not 0 < (end-start).total_seconds() <= 86400:
        raise WorkloadError('Slow-log analysis requires one schema and at most 24 hours')
    # _read has a 101-row protocol bound. Read a declared 100-row slice, not an
    # unbounded server log, and disclose that it is a sample of the time window.
    reader._connection.time_zone = '+00:00'
    rows = reader._read('SELECT /*+ MAX_EXECUTION_TIME(5000) */ start_time,CAST(query_time AS CHAR) AS query_time,'
        'CAST(lock_time AS CHAR) AS lock_time,rows_sent,rows_examined,'
        'IF(OCTET_LENGTH(sql_text)<=65536,sql_text,NULL) AS sql_text '
        'FROM mysql.slow_log WHERE db=%s AND start_time>=%s AND start_time<%s '
        'ORDER BY start_time DESC LIMIT 101', (schema, start, end))
    entries = []
    for row in rows[:100]:
        text = row['sql_text']
        if isinstance(text, dict) and set(text) == {'hex'}:
            text = bytes.fromhex(text['hex']).decode('utf8', errors='strict')
        if not isinstance(text, str):
            raise WorkloadError('The native log SQL encoding is unavailable')
        def seconds(value):
            # mysql_catalog._value serializes timedeltas using str().
            parts = str(value).split(':')
            if len(parts) != 3 or 'day' in parts[0]:
                raise WorkloadError('The native slow-log duration is unsupported')
            return Decimal(parts[0])*3600 + Decimal(parts[1])*60 + Decimal(parts[2])
        entries.append({'sql': text, 'schema_name': schema, 'query_time': seconds(row['query_time']),
            'lock_time': seconds(row['lock_time']), 'rows_sent': int(row['rows_sent']),
            'rows_examined': int(row['rows_examined'])})
    return aggregate_log(reader, entries, source='mysql.slow_log', truncated=len(rows)>100,
        window={'schema_name': schema, 'start_utc': options['start_utc'], 'end_utc': options['end_utc']})


def parse_slow_file(text, schema, start, end):
    """Parse native long-format MySQL logs as data; never execute their SQL."""
    if not isinstance(text, str) or not text or len(text.encode('utf8')) > MAX_LOG_BYTES or '\x00' in text:
        raise WorkloadError('Upload at most 1 MiB of UTF-8 native MySQL slow-log text')
    schema_name(schema)
    if schema is None or not 0 < (end-start).total_seconds() <= 86400:
        raise WorkloadError('Select one schema and a UTC window of at most 24 hours')
    # Native file logs have no escaping for embedded log-looking SQL lines.
    # Refuse ambiguous or partial entries instead of claiming exact coverage.
    blocks = re.split(r'(?m)^# Time: ', text)
    entries, current_schema = [], None
    if len(blocks) <= 1 or len(blocks)-1 > MAX_LOG_ENTRIES:
        raise WorkloadError('Upload 1–500 complete native long-format slow-log entries')
    for block in blocks[1:]:
        lines = block.splitlines()
        if len(lines) < 5 or not lines[1].startswith('# User@Host: ') or not lines[2].startswith('# Query_time: '):
            raise WorkloadError('Slow-log framing is incomplete or ambiguous')
        observed = cutoff(lines[0])
        metrics = dict(re.findall(r'([A-Za-z_]+): ([0-9]+(?:\.[0-9]+)?)', lines[2]))
        if not {'Query_time', 'Lock_time', 'Rows_sent', 'Rows_examined'} <= metrics.keys():
            raise WorkloadError('Native slow-log timing fields are incomplete')
        body = lines[3:]
        if body and body[0].startswith('use ') and body[0].endswith(';'):
            current_schema = body.pop(0)[4:-1]
        if not body or not re.fullmatch(r'SET (?:(?:last_insert_id|insert_id)=[0-9]+,)*timestamp=[0-9]+(?:\.[0-9]+)?;', body.pop(0)):
            raise WorkloadError('Native slow-log timestamp framing is unavailable')
        sql = '\n'.join(body).strip()
        if not sql.endswith(';') or re.search(r'(?m)^# (?:Time:|User@Host:|Query_time:)', sql):
            raise WorkloadError('Slow-log SQL framing is incomplete or ambiguous')
        if current_schema is None and start <= observed < end:
            raise WorkloadError('The uploaded slow log has no preceding native schema context')
        if current_schema == schema and start <= observed < end:
            entries.append({'sql': sql, 'schema_name': current_schema,
                'query_time': Decimal(metrics['Query_time']), 'lock_time': Decimal(metrics['Lock_time']),
                'rows_sent': int(metrics['Rows_sent']), 'rows_examined': int(metrics['Rows_examined'])})
    return entries


def aggregate_log(reader, entries, *, source, truncated=False, window=None):
    groups, unparsed = {}, []
    deadline = time.monotonic() + 15
    if sum(len(entry['sql'].encode('utf8')) for entry in entries) > MAX_LOG_BYTES:
        raise WorkloadError('The selected native slow-log SQL exceeds 1 MiB; narrow the input window')
    with localcontext() as context:
        context.prec = 64
        for index, entry in enumerate(entries):
            if time.monotonic() >= deadline:
                raise WorkloadError('Slow-log normalization exceeded 15 seconds; narrow the selected input')
            if len(entry['sql'].encode('utf8')) > 65536:
                raise WorkloadError('A log statement exceeds the native digest inspection limit')
            # MySQL owns lexical normalization, including its SQL grammar.
            # Bound parameters are data, never native statement dispatch.
            try:
                normalized = reader._read('SELECT STATEMENT_DIGEST(%s) AS digest,'
                    'STATEMENT_DIGEST_TEXT(%s) AS digest_text', (entry['sql'], entry['sql']))[0]
            except Exception as error:
                if getattr(error, 'errno', None) != 3676:  # ER_PARSE_ERROR_IN_DIGEST_FN
                    raise
                # Native logs include non-SQL administrator commands and failed
                # syntax. Do not emulate their normalization or retain raw text.
                unparsed.append({'input_index': index, 'error_code': error.errno,
                                 'sqlstate': getattr(error, 'sqlstate', None)})
                continue
            if not normalized['digest'] or not normalized['digest_text']:
                unparsed.append({'input_index': index, 'reason': 'native-digest-unavailable'})
                continue
            key = entry['schema_name'], normalized['digest']
            group = groups.setdefault(key, {'schema_name': key[0], **normalized, 'count': 0,
                'total_seconds': Decimal(0), 'lock_seconds': Decimal(0), 'rows_sent': 0, 'rows_examined': 0})
            group['count'] += 1
            for name, field in [('total_seconds', 'query_time'), ('lock_seconds', 'lock_time'),
                                ('rows_sent', 'rows_sent'), ('rows_examined', 'rows_examined')]:
                group[name] += entry[field]
        result = []
        for group in sorted(groups.values(), key=lambda g: g['total_seconds'], reverse=True):
            group['mean_seconds'] = group['total_seconds'] / group['count']
            result.append({key: str(value) if isinstance(value, (int, Decimal)) else value for key, value in group.items()})
    return {'source': source, 'window': window, 'entries': len(entries), 'truncated': truncated,
        'limit': 100 if source == 'mysql.slow_log' else MAX_LOG_ENTRIES, 'rows': result,
        'unparsed': unparsed, 'normalized_entries': len(entries)-len(unparsed),
        'coverage': 'Selected bounded input only; not a complete server workload. No raw SQL retained.',
        'normalization': 'native STATEMENT_DIGEST / STATEMENT_DIGEST_TEXT; source SQL is bound data, never executed'}
