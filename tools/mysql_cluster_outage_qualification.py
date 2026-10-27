"""Real, owned Cluster outage and unreachable-member repair acceptance."""
import json
from pathlib import Path
import secrets
import time


def qualify(app, client, service, post, server_id, owned, output, use_c, repair_families=None):
    import mysql.connector
    from flask import url_for
    from pgadmin.model import db, Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    output = Path(output)
    proof = {'complete': False, 'checks': [], 'operations': [], 'history_testing': 'not run'}
    registrations = []
    with app.test_request_context('/'):
        seed = db.session.get(Server, server_id)
        for index, peer in enumerate(owned['peers']):
            if index == 0:
                item = seed
            else:
                item = Server(user_id=seed.user_id, servergroup_id=seed.servergroup_id,
                    name='Owned Cluster outage '+peer['server_uuid'], host=peer['host'], port=3306,
                    username='root', maintenance_db=None, save_password=0)
                item._cde_endpoint_registration = registration_profile('mysql-native')
                item._cde_endpoint_route_configuration = {'host': peer['host'], 'port': 3306,
                    'user': 'root', 'use_pure': not use_c, 'credential_kinds': ['database_password']}
                db.session.add(item); db.session.commit()
            registrations.append({'server_id': item.id,
                'verify': url_for('NODE-server.verify_endpoint_id', gid=item.servergroup_id, sid=item.id),
                'url': url_for('NODE-server.cde_workspace_id', gid=item.servergroup_id, sid=item.id)})
    for item in registrations[1:]:
        assert client.post(item['verify'], json={'password': 'true'}).get_json()['success']

    def connect(index):
        return mysql.connector.connect(host=owned['peers'][index]['host'], port=3306, user='root',
            password='true', use_pure=not use_c, autocommit=True, connection_timeout=2, read_timeout=5)

    def query(connection, source, parameters=()):
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(source, parameters)
            return cursor.fetchall() if cursor.with_rows else []
        finally:
            cursor.close()

    def sql(index, source, parameters=()):
        connection = connect(index)
        try: return query(connection, source, parameters)
        finally: connection.close()

    def until(observation, timeout=60):
        deadline = time.monotonic()+timeout
        while True:
            try:
                value = observation()
                if value: return value
            except mysql.connector.Error:
                if time.monotonic() >= deadline: raise
            if time.monotonic() >= deadline: raise TimeoutError('Owned Cluster outage observation deadline')
            time.sleep(.2)

    def http(action, request, peer=0):
        response = client.post(registrations[peer]['url'], json={
            'action': 'mysql_topology_'+action, 'request': request})
        value = response.get_json()
        if response.status_code != 200 or not value.get('success'):
            (output/'outage-http-failure.json').write_text(json.dumps(value, indent=2)+'\n')
            raise AssertionError('Native Cluster outage request failed: '+action)
        return value['data']

    def execute(operation, arguments, peer=0, witnesses=()):
        selected = {'operation': operation, 'arguments_json': json.dumps(arguments),
            'context_name': '', 'context_options_json': '{}', 'use_advertised_endpoint': True,
            'witness_server_ids': [registrations[index]['server_id'] for index in witnesses],
            'target_confirmation': owned['peers'][peer]['server_uuid'], 'timeout_seconds': 180}
        reviewed = http('review', {'options': selected}, peer)
        request = {**{key: reviewed[key] for key in ('job_id', 'review_digest')}, 'confirmed': True}
        value = http('start', request, peer)
        deadline = time.monotonic()+200
        while value['state'] in {'dispatching', 'active', 'cancel_requested'}:
            if time.monotonic() >= deadline: raise TimeoutError('Native Cluster outage operation deadline')
            time.sleep(.1); value = http('status', {'job_id': value['job_id']}, peer)
        (output/'outage-last-operation.json').write_text(json.dumps(value, indent=2)+'\n')
        proof['operations'].append({'method': operation, 'job_id': value['job_id'],
            'outcome': value['native_operation_outcome']})
        assert value['native_operation_outcome'] == 'returned', value.get('native_error') or value.get('error_type')
        assert value['native_process_termination_confirmed'] and not value['workload_readiness_verified']
        assert http('start', request, peer)['native_operation_outcome'] == 'returned'
        return value

    controls = Path(owned['private_key']).parent.parent/'mysql-router-fixture240/controls'
    def control(index, operation):
        name = 'outage-'+secrets.token_hex(8)
        request = controls/(name+'.request.json'); answer = controls/(name+'.answer.json')
        request.write_text(json.dumps({'operation': operation, 'container': owned['peers'][index]['container']})+'\n')
        until(lambda: answer.exists(), 30)
        assert json.loads(answer.read_text())['return_code'] == 0

    pending = None
    try:
        if repair_families is not None:
            from mysql_topology_repair_qualification import qualify as repair
            repair(execute, http, sql, connect, query, control, until, registrations,
                owned, output, use_c, proof, post, *repair_families)
            proof['complete'] = True
            return proof
        initial = sql(0, 'SELECT MEMBER_ID,MEMBER_STATE,MEMBER_ROLE FROM performance_schema.replication_group_members ORDER BY MEMBER_ID')
        assert len(initial) == 3 and all(row['MEMBER_STATE'] == 'ONLINE' for row in initial)
        primary = next(index for index, peer in enumerate(owned['peers']) if peer['server_uuid'] ==
            next(row['MEMBER_ID'] for row in initial if row['MEMBER_ROLE'] == 'PRIMARY'))
        schema = 'sr_outage_'+secrets.token_hex(6)
        sql(primary, 'CREATE DATABASE '+schema+' CHARACTER SET utf8mb4')
        sql(primary, 'CREATE TABLE '+schema+'.t(id BIGINT PRIMARY KEY,body TEXT,payload LONGBLOB)')
        expected = [{'id': '9007199254740993', 'body': 'outage 雪', 'payload': '00FF'}]
        sql(primary, 'INSERT INTO '+schema+'.t VALUES(%s,%s,%s)', (9007199254740993, 'outage 雪', b'\x00\xff'))
        data = 'SELECT CAST(id AS CHAR) AS id,body,HEX(payload) AS payload FROM '+schema+'.t ORDER BY id'
        for index in range(3): until(lambda index=index: sql(index, data) == expected)
        pending = connect(primary); query(pending, 'START TRANSACTION')
        query(pending, 'INSERT INTO '+schema+'.t VALUES(2,\'pending rollback\',NULL)')
        for index in range(3): sql(index, 'SET PERSIST group_replication_start_on_boot=OFF')
        for index in range(3): control(index, 'crash')
        try: pending.close()
        except mysql.connector.Error: pass
        pending = None
        for index in (0, 1):
            control(index, 'start')
            until(lambda index=index: sql(index, 'SELECT @@server_uuid AS uuid') ==
                [{'uuid': owned['peers'][index]['server_uuid']}])
        try:
            connection = connect(2); connection.close()
        except mysql.connector.Error: pass
        else: raise AssertionError('Owned third member must remain independently unreachable')
        for index in (0, 1):
            assert not sql(index, "SELECT MEMBER_ID FROM performance_schema.replication_group_members WHERE MEMBER_STATE='ONLINE'")
        name = sql(0, 'SELECT cluster_name FROM mysql_innodb_cluster_metadata.clusters')[0]['cluster_name']
        execute('instance.reboot_cluster', [name, {'force': True}], witnesses=(1,))
        until(lambda: len(sql(0, "SELECT MEMBER_ID FROM performance_schema.replication_group_members WHERE MEMBER_STATE='ONLINE'")) == 2)
        for index in (0, 1): assert sql(index, data) == expected
        proof['checks'].append('actual-three-server-crash-two-server-restart-and-native-forced-complete-outage-reboot-with-independently-unreachable-third-member')
        control(2, 'start'); until(lambda: sql(2, 'SELECT @@server_uuid AS uuid') == [{'uuid': owned['peers'][2]['server_uuid']}])
        execute('cluster.rejoin_instance', [{'server_id': registrations[2]['server_id']},
            {'recoveryMethod': 'incremental'}], witnesses=(1, 2))
        until(lambda: len(sql(0, "SELECT MEMBER_ID FROM performance_schema.replication_group_members WHERE MEMBER_STATE='ONLINE'")) == 3)
        for index in range(3): assert sql(index, data) == expected
        current = sql(0, 'SELECT MEMBER_ID,MEMBER_STATE,MEMBER_ROLE FROM performance_schema.replication_group_members ORDER BY MEMBER_ID')
        primary = next(index for index, peer in enumerate(owned['peers']) if peer['server_uuid'] ==
            next(row['MEMBER_ID'] for row in current if row['MEMBER_ROLE'] == 'PRIMARY'))
        sql(primary, 'INSERT INTO '+schema+'.t VALUES(3,\'after repair\',NULL)')
        for index in range(3): until(lambda index=index: len(sql(index, data)) == 2)
        proof['checks'].append('native-incremental-member-rejoin-independent-three-member-replication-committed-exact-data-pending-rollback-and-new-write-catch-up')
        proof.update(complete=True, native_members=current)
    finally:
        if pending is not None:
            try: pending.close()
            except mysql.connector.Error: pass
        (output/'outage-summary.json').write_text(json.dumps(proof, indent=2)+'\n')
    return proof
