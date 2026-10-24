"""Live native Router metadata methods through reviewed topology operations."""
from copy import deepcopy
import json
from pathlib import Path
import secrets
import time


def qualify(post,selected,credentials,owned,output,use_c,keep_live=False):
    import mysql.connector
    output=Path(output);proof={'complete':False,'checks':[],'history_testing':'not run','operations':[]}
    def wait(value,prefix='mysql_router_'):
        deadline=time.monotonic()+150
        while value['state'] in {'dispatching','active','cancel_requested'}:
            if time.monotonic()>deadline:raise TimeoutError('Owned native Router metadata operation deadline')
            time.sleep(.1);value=post('status',{'job_id':value['job_id']},prefix=prefix)
        return value
    def admitted(value,ssh=False):return {**{name:value[name] for name in ('job_id','review_digest')},'confirmed':True,**({'credentials':credentials} if ssh else {})}
    options=deepcopy(selected);options['extra_arguments']=['--name=sr-live-router-'+secrets.token_hex(7),'--conf-skip-x-protocol']
    reviewed=post('review',{'options':options,'credentials':credentials})
    assert reviewed['source_connection_class']==('CharsetCMySQLConnection' if use_c else 'CharsetMySQLConnection')
    bootstrap=wait(post('start',admitted(reviewed,True)))
    assert bootstrap['state']=='native_process_returned' and bootstrap['remote_receipt']['result']['return_code']==0
    router_id=int(bootstrap['remote_receipt']['deployment_observation']['native_router_ids'][0])
    def service(operation,reference):
        current={**options,'operation':operation,'binding_job_id':reference['job_id'],
            'service':{'manager':'systemd','name':'sr-live-router-'+secrets.token_hex(5)+'.service'} if operation=='install_service' else reference['options']['service'],
            'disconnect_all_clients':operation in {'service_stop','service_restart'}}
        value=wait(post('start',admitted(post('review',{'options':current,'credentials':credentials}),True)))
        assert value['state']=='native_process_returned' and value['remote_receipt']['result']['return_code']==0
        if operation=='service_start':assert value['remote_receipt']['service_after']['native_process']['unit_control_group_verified']
        return value
    installed=service('install_service',bootstrap);started=service('service_start',installed);stopped=False
    connection=mysql.connector.connect(host=owned['peers'][0]['host'],port=3306,user='root',password='true',use_pure=not use_c,autocommit=True)
    def sql(source,parameters=()):
        cursor=connection.cursor(dictionary=True)
        try:cursor.execute(source,parameters);return cursor.fetchall()
        finally:cursor.close()
    def selected_call(operation,arguments):
        return {'operation':'cluster.'+operation,'arguments_json':json.dumps(arguments),'context_name':'','context_options_json':'{}',
            'use_advertised_endpoint':True,'witness_server_ids':[],'target_confirmation':owned['peers'][0]['server_uuid'],'timeout_seconds':120}
    def call(operation,arguments=(),read=False):
        request={'options':selected_call(operation,list(arguments))}
        if read:value=post('inspect_native',request,prefix='mysql_topology_')
        else:
            review=post('review',request,prefix='mysql_topology_');value=post('start',admitted(review),prefix='mysql_topology_')
        value=wait(value,'mysql_topology_');proof['operations'].append({'method':operation,'job_id':value['job_id'],'outcome':value['native_operation_outcome']})
        (output/'metadata-last-operation.json').write_text(json.dumps(value,indent=2)+'\n')
        assert value['native_operation_outcome']=='returned' and value['native_process_termination_confirmed'],value.get('native_error') or value.get('error_type')
        control=value['result']['control'];assert control['observation_error'] is None
        return json.loads(control['result_json'])
    try:
        row=sql('SELECT router_id,router_name,address,CAST(options AS CHAR) AS options FROM mysql_innodb_cluster_metadata.routers WHERE router_id=%s',(router_id,))[0]
        label=row['address']+'::'+row['router_name']
        if keep_live:
            proof.update(complete=True,desktop_fixture_only=True,router_id=router_id,native_router_label=label,
                started_job_id=started['job_id'],started_options=started['options'])
            (output/'metadata-live-setup.json').write_text(json.dumps(proof,indent=2)+'\n')
            return proof
        listed=call('list_routers',read=True)
        (output/'live-routers.json').write_text(json.dumps(listed,indent=2)+'\n')
        assert label in listed['routers'],listed
        configured=call('router_options',[{'router':label,'extended':2}],read=True)
        (output/'live-router-options.json').write_text(json.dumps(configured,indent=2)+'\n')
        stale=post('review',{'options':selected_call('set_router_option',[label,'stats_updates_frequency',11])},prefix='mysql_topology_')
        call('set_router_option',[label,'stats_updates_frequency',7])
        post('start',admitted(stale),refused=True,prefix='mysql_topology_')
        observed=json.loads(sql('SELECT CAST(options AS CHAR) AS options FROM mysql_innodb_cluster_metadata.routers WHERE router_id=%s',(router_id,))[0]['options'])
        def values(value,key):
            if isinstance(value,dict):return ([value[key]] if key in value else [])+[found for item in value.values() for found in values(item,key)]
            if isinstance(value,list):return [found for item in value for found in values(item,key)]
            return []
        assert 7 in values(observed,'stats_updates_frequency'),observed
        call('set_router_option',[label,'stats_updates_frequency',None])
        observed=json.loads(sql('SELECT CAST(options AS CHAR) AS options FROM mysql_innodb_cluster_metadata.routers WHERE router_id=%s',(router_id,))[0]['options'])
        assert not values(observed,'stats_updates_frequency') or all(item is None for item in values(observed,'stats_updates_frequency')),observed
        proof['checks'].append('live-native-Router-list-selected-options-set-reset-independent-metadata-and-stale-review-refusal')
        routed=mysql.connector.connect(host=owned['router_address'],port=options['base_port']+4,user='root',password='true',use_pure=not use_c,connection_timeout=5,read_timeout=5)
        try:
            cursor=routed.cursor();cursor.execute('SELECT @@server_uuid,9007199254740993');uuid,integer=cursor.fetchone()
            assert uuid in {peer['server_uuid'] for peer in owned['peers']} and integer==9007199254740993
        finally:routed.close()
        proof['checks'].append('actual-native-automatic-read-write-split-classic-route-preserves-exact-native-bigint')
        service('service_stop',started);stopped=True
        call('remove_router_metadata',[label])
        assert sql('SELECT COUNT(*) AS n FROM mysql_innodb_cluster_metadata.routers WHERE router_id=%s',(router_id,))==[{'n':0}]
        assert label not in call('list_routers',read=True)['routers']
        proof['checks'].append('reviewed-native-selected-Router-metadata-removal-independent-row-absence-and-list-refresh')
        proof.update(complete=True,router_id=router_id,native_router_label=label)
    finally:
        if not stopped and not keep_live:service('service_stop',started)
        connection.close();(output/'metadata-summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof
