"""Dedicated native inspection does not end or expose a replacement user statement."""


def qualify(connection, provider, route, root, permissions):
    from pgadmin.cdeadmin.providers.firebird.monitoring import FirebirdMonitor
    monitor = FirebirdMonitor(permissions, route)
    cursor = connection.cursor()
    try:
        cursor.execute('CREATE TABLE INSPECT_DATA (ID INTEGER)')
        connection.commit()
        cursor.execute('INSERT INTO INSPECT_DATA VALUES (7)')
        transaction = connection.main_transaction.info.id
        attachment = connection.info.id
        query = 'SELECT D.ID FROM INSPECT_DATA D CROSS JOIN RDB$TYPES A CROSS JOIN RDB$TYPES B /* ' + 'ü' * 5000 + ' */'
        cursor.execute(query)
        assert cursor.fetchone() == (7,)
        sample = monitor.sample()
        assert sample['status'] in {'available', 'partial'}, sample
        rows = sample['groups']['statement_details']['values']['rows']
        candidates = [row for row in rows if row['attachment_id'] == str(attachment)]
        assert candidates, rows
        references = [{key: row[key] for key in ('statement_id', 'attachment_id', 'compiled_statement_id', 'timestamp')}
                      for row in candidates]
        detail = reference = None
        for candidate in references:
            observed = monitor.inspect_statement({**candidate, 'source_epoch': sample['source_epoch']})
            if observed.get('sql_text', {}).get('value', '').startswith('SELECT D.ID FROM INSPECT_DATA'):
                detail, reference = observed, candidate
                break
        assert detail and detail['status'] == 'available', candidates
        assert detail['sql_text']['truncated'] and len(detail['sql_text']['value']) == 4096, detail
        assert detail['explained_plan']['value'] and 'INSPECT_DATA' in detail['explained_plan']['value'], detail
        assert not monitor._connection.main_transaction.is_active()
        assert connection.main_transaction.info.id == transaction
        changed = monitor.inspect_statement({**reference, 'source_epoch': sample['source_epoch'],
                                             'compiled_statement_id': str(int(reference['compiled_statement_id'] or '0') + 1)})
        assert changed['status'] == 'changed' and 'sql_text' not in changed, (changed['status'], reference, monitor.sample()['groups']['statement_details'])
        cursor.close()
        gone = monitor.inspect_statement({**reference, 'source_epoch': sample['source_epoch']})
        assert gone['status'] in {'gone', 'changed'} and 'sql_text' not in gone, gone
        cursor = connection.cursor()
        cursor.execute('SELECT COUNT(*) FROM INSPECT_DATA')
        assert cursor.fetchone() == (1,)
        assert connection.main_transaction.info.id == transaction
        connection.rollback()
        return {'native_sql_and_plan': True, 'native_server_text_bound': True,
                'compiled_identity_change_refused': True, 'released_statement_not_reused': True,
                'monitoring_transactions_ended': True, 'user_pending_work_preserved': True}
    finally:
        cursor.close()
        monitor.close()
