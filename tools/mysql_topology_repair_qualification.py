"""Native ReplicaSet and ClusterSet failures, repair and routed workload."""
from copy import deepcopy
import json
from pathlib import Path
import secrets
import time


def qualify(execute, http, sql, connect, query, control, until, registrations,
            owned, output, use_c, proof, post, chosen, credentials):
    import mysql.connector
    from mysql_router_metadata_qualification import qualify as router_setup
    output = Path(output)
    def uri(index): return {'server_id': registrations[index]['server_id']}
    def wait_job(value):
        deadline = time.monotonic()+150
        while value['state'] in {'dispatching','active','cancel_requested'}:
            if time.monotonic() >= deadline: raise TimeoutError('Owned native Router repair control deadline')
            time.sleep(.1); value = post('status', {'job_id': value['job_id']})
        assert value['state'] == 'native_process_returned'
        assert value['remote_receipt']['result']['return_code'] == 0
        return value
    def stop_router(live):
        selected = {**live['started_options'], 'operation': 'service_stop',
            'binding_job_id': live['started_job_id'], 'disconnect_all_clients': True}
        reviewed = post('review', {'options': selected, 'credentials': credentials})
        wait_job(post('start', {**{key: reviewed[key] for key in ('job_id','review_digest')},
            'confirmed': True, 'credentials': credentials}))
    def routed(port):
        return mysql.connector.connect(host=owned['router_address'],port=port,user='root',password='true',
            use_pure=not use_c,autocommit=True,connection_timeout=3,read_timeout=5)
    def result(value):
        control = value['result']['control']
        assert control['observation_error'] is None
        return json.loads(control['result_json'])
    def metadata(family, live, directory):
        label = live['native_router_label']
        listed = result(execute(family+'.list_routers', []))
        assert label in listed['routers'], listed
        configured = result(execute(family+'.router_options', [{'router':label,'extended':2}]))
        execute(family+'.set_router_option', [label, 'stats_updates_frequency', 9])
        stored = json.loads(sql(0, 'SELECT CAST(options AS CHAR) AS value FROM mysql_innodb_cluster_metadata.routers WHERE router_id=%s',
            (live['router_id'],))[0]['value'])
        def values(value):
            if isinstance(value, dict):
                return ([value['stats_updates_frequency']] if 'stats_updates_frequency' in value else []) + [found for item in value.values() for found in values(item)]
            if isinstance(value, list): return [found for item in value for found in values(item)]
            return []
        assert 9 in values(stored), stored
        execute(family+'.set_router_option', [label, 'stats_updates_frequency', None])
        reset = json.loads(sql(0, 'SELECT CAST(options AS CHAR) AS value FROM mysql_innodb_cluster_metadata.routers WHERE router_id=%s',
            (live['router_id'],))[0]['value'])
        assert all(value is None for value in values(reset)), reset
        (directory/'live-metadata.json').write_text(json.dumps({'listed': listed,'options':configured,'set':stored,'reset':reset},indent=2)+'\n')
        proof['checks'].append(family+'-actual-live-native-Router-list-options-set-reset-and-independent-metadata')

    def standalone(index):
        return (not sql(index,"SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA='mysql_innodb_cluster_metadata'") and
            not sql(index,"SELECT CHANNEL_NAME FROM performance_schema.replication_connection_configuration WHERE CHANNEL_NAME NOT IN ('group_replication_applier','group_replication_recovery')") and
            not sql(index,'SHOW REPLICAS'))
    if sql(0,"SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA='mysql_innodb_cluster_metadata' AND TABLE_NAME='clusters'"):
        execute('cluster.dissolve', [{'force': True}])
    for index in range(3): until(lambda index=index: standalone(index))
    for index in range(3):
        sql(index, 'SET GLOBAL super_read_only=OFF')
        execute('instance.configure_replica_set', [{'restart': True}], peer=index)
    execute('instance.create_replica_set', ['sr_repair_replicas', {'gtidSetIsComplete': True}])
    for index in (1,2):
        execute('replica_set.add_instance', [uri(index), {'recoveryMethod':'clone','recoveryProgress':0}], witnesses=tuple(range(index+1)))
    for family in ('replica_set', 'cluster_set'):
        if family == 'cluster_set':
            execute('replica_set.dissolve', [{'force': True}], peer=1)
            # Native dissolution can return before the old primary's outgoing
            # replica registrations disappear. Native configureInstance uses
            # those registrations as well as incoming channels to classify an
            # unmanaged asynchronous topology. Observe both before reuse.
            for index in range(3): until(lambda index=index: standalone(index))
            for index in range(3):
                sql(index, 'SET GLOBAL super_read_only=OFF')
                execute('instance.configure_cluster', [{'restart': True}], peer=index)
            execute('instance.create_cluster', ['sr_repair_primary', {'gtidSetIsComplete':True,'communicationStack':'MYSQL'}])
            execute('cluster.create_cluster_set', ['sr_repair_domain'])
            for index in (1,2):
                execute('cluster_set.create_replica_cluster', [uri(index), 'sr_repair_replica'+str(index),
                    {'recoveryMethod':'clone','recoveryProgress':0}], witnesses=tuple(range(index+1)))
        directory = output/family; directory.mkdir()
        selected = deepcopy(chosen); selected['directory'] = '/opt/sr-repair-router-'+secrets.token_hex(8)
        live = router_setup(post,selected,credentials,owned,directory,use_c,True,family)
        pending = None
        try:
            metadata(family, live, directory)
            port = live['started_options']['base_port']
            schema = 'sr_'+family+'_'+secrets.token_hex(5)
            connection = routed(port)
            try:
                assert query(connection, 'SELECT @@server_uuid AS uuid') == [{'uuid':owned['peers'][0]['server_uuid']}]
                assert query(connection, "SHOW SESSION STATUS LIKE 'Ssl_cipher'")[0]['Value']
                query(connection, 'CREATE DATABASE '+schema+' CHARACTER SET utf8mb4')
                query(connection, 'CREATE TABLE '+schema+'.t(id BIGINT PRIMARY KEY,body TEXT,payload LONGBLOB)')
                query(connection, 'INSERT INTO '+schema+'.t VALUES(%s,%s,%s)',(9007199254740993,'routed '+family+' 雪',b'\x00\xff'))
            finally: connection.close()
            data = 'SELECT CAST(id AS CHAR) AS id,body,HEX(payload) AS payload FROM '+schema+'.t ORDER BY id'
            expected = [{'id':'9007199254740993','body':'routed '+family+' 雪','payload':'00FF'}]
            for index in range(3): until(lambda index=index: sql(index,data)==expected)
            pending = routed(port); query(pending,'START TRANSACTION')
            query(pending,'INSERT INTO '+schema+'.t VALUES(2,\'pending rollback\',NULL)')
            if family == 'cluster_set': sql(0,'SET PERSIST group_replication_start_on_boot=OFF')
            control(0,'crash')
            try:
                connection = connect(0); connection.close()
            except mysql.connector.Error: pass
            else: raise AssertionError('Original primary must be independently unreachable')
            if family == 'replica_set':
                execute('replica_set.force_primary',[uri(1),{'timeout':15}],peer=1)
            else:
                execute('cluster_set.force_primary',['sr_repair_replica1',{'timeout':15}],peer=1)
            def current_route():
                connection = routed(port)
                try:
                    return query(connection,'SELECT @@server_uuid AS uuid')==[{'uuid':owned['peers'][1]['server_uuid']}]
                finally: connection.close()
            until(current_route)
            connection = routed(port)
            try:
                assert query(connection,data)==expected
                query(connection,'INSERT INTO '+schema+'.t VALUES(3,\'after failover\',NULL)')
            finally: connection.close()
            until(lambda: len(sql(2,data))==2)
            proof['checks'].append(family+'-actual-primary-crash-native-forced-promotion-TLS-Router-primary-change-exact-committed-data-pending-rollback-and-new-write-replication')
            try: pending.close()
            except mysql.connector.Error: pass
            pending = None
            control(0,'start')
            until(lambda: sql(0,'SELECT @@server_uuid AS uuid')==[{'uuid':owned['peers'][0]['server_uuid']}])
            if family == 'replica_set':
                execute('replica_set.rejoin_instance',[uri(0),{'recoveryMethod':'incremental'}],peer=1,witnesses=(0,2))
            else:
                execute('instance.reboot_cluster',['sr_repair_primary',{}],peer=0,witnesses=(1,2))
                execute('cluster_set.rejoin_cluster',['sr_repair_primary'],peer=1)
            for index in range(3): until(lambda index=index: len(sql(index,data))==2)
            execute(family+'.set_primary',[uri(2)] if family=='replica_set' else ['sr_repair_replica2'],peer=1)
            connection = routed(port)
            try:
                deadline = time.monotonic()+30
                while query(connection,'SELECT @@server_uuid AS uuid') != [{'uuid':owned['peers'][2]['server_uuid']}]:
                    connection.close()
                    if time.monotonic() >= deadline: raise TimeoutError('Native Router planned switchover deadline')
                    time.sleep(.2); connection=routed(port)
                assert len(query(connection,data))==2
                query(connection,'INSERT INTO '+schema+'.t VALUES(4,\'after switchover\',NULL)')
            finally: connection.close()
            for index in range(3): until(lambda index=index: len(sql(index,data))==3)
            proof['checks'].append(family+'-original-primary-native-rejoin-independent-three-target-data-and-planned-switchover-with-routed-write-catch-up')
        finally:
            if pending is not None:
                try: pending.close()
                except mysql.connector.Error: pass
            stop_router(live)
    execute('cluster_set.dissolve',[{'force':True}],peer=2)
    for index in range(3):
        sql(index,'SET GLOBAL super_read_only=OFF')
        execute('instance.configure_cluster',[{'restart':True}],peer=index)
    execute('instance.create_cluster',['sr_router_product242',{'gtidSetIsComplete':True,'communicationStack':'MYSQL'}])
    for index in (1,2):
        execute('cluster.add_instance',[uri(index),{'recoveryMethod':'clone','recoveryProgress':0}],witnesses=tuple(range(index+1)))
    proof['checks'].append('owned-native-fixture-restored-to-three-member-Cluster-through-reviewed-application-methods')
