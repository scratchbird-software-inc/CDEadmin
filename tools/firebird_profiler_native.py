"""Native profiler evidence using only the gate's disposable database."""
import time


def qualify(_connection, client, route):
    connection = client.open_session({'route': route})
    try:
        return _qualify(connection, client, route)
    finally:
        client.close_session(connection)


def _qualify(connection, client, route):
    def sql(source):
        with connection.cursor() as cursor:
            cursor.execute(source)
            return cursor.fetchall() if cursor.description else []
    sql('CREATE TABLE PROFILE_TEST (ID INTEGER)')
    connection.commit()
    sql('INSERT INTO PROFILE_TEST VALUES (10)')
    original_transaction = connection.main_transaction.info.id
    def run(source):
        query = client.submit_query(connection, {'source': source, 'parameters': [],
            'output_policy': {'firebird_profile': True, 'firebird_statistics': True}, '_provider_route': route})
        deadline = time.monotonic() + 30
        while not query.done and time.monotonic() < deadline:
            time.sleep(.02)
        assert query.done, 'Native profiler qualification timed out'
        return client.describe_result(query)
    result = run('EXECUTE BLOCK AS DECLARE I INTEGER; BEGIN I = 0; WHILE (I < 3) DO BEGIN INSERT INTO PROFILE_TEST VALUES (:I); I = I + 1; END END')
    payload = result['payload']
    assert payload['execution_state'] == 'succeeded', payload
    report = payload['profiling']
    assert report['state'] == 'complete', report
    assert report['sections']['psql']['rows'], report
    statistics = payload['query_statistics']
    assert statistics['complete'], statistics
    assert statistics['deltas']['record_inserts'] >= 3, statistics
    assert statistics['elapsed'] > 0
    assert connection.main_transaction.info.id == original_transaction
    assert sql('SELECT COUNT(*) FROM PROFILE_TEST') == [(4,)]
    connection.rollback()
    assert sql('SELECT COUNT(*) FROM PROFILE_TEST') == [(0,)]
    connection.rollback()
    # Observe real SQL record-source counters under the same wrapper.
    result = run('SELECT RDB$RELATION_NAME FROM RDB$RELATIONS')
    assert result['payload']['profiling']['sections']['record_sources']['rows'], result
    assert result['payload']['profiling']['state'] == 'complete', result
    connection.rollback()
    failure = run('SELECT NONEXISTENT_PROFILE_COLUMN FROM PROFILE_TEST')
    assert failure['payload']['execution_state'] == 'failed', failure
    assert failure['payload']['profiling']['state'] == 'complete', failure
    if connection.main_transaction.is_active():
        connection.rollback()
    return {'passed': True, 'psql': report, 'statistics': statistics, 'record_sources': result['payload']['profiling'],
            'failed_sql_profile': failure['payload']['profiling'],
            'user_transaction_preserved_and_rollback_verified': True}
