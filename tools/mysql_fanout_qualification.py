"""Independently observe native fanout target selection and per-member results."""
import json


def qualify(context, seed, peers, execute, http, options, sql, registrations, seeds):
    checks=[]
    def run(statement, instances='all', native_options=None):
        arguments=[statement,instances]+([native_options] if native_options is not None else [])
        value=execute(context+'.execute',arguments,seed)
        assert value['result']['control']['observation_error'] is None,value
        return value,json.loads(value['result']['control']['result_json'])
    def maximum(peer):
        return int(sql(peer,'SELECT @@global.max_connections AS n')[0]['n'])
    original={peer:maximum(peer) for peer in peers}
    target=max(original.values())+17
    try:
        _value,result=run("SELECT @@server_uuid AS uuid,CAST(9223372036854775808 AS UNSIGNED) AS wide,'雪' AS body")
        expected={seeds[peer]['identity']['server_uuid'] for peer in peers}
        assert {row['output'][0]['rows'][0][0] for row in result}==expected,result
        assert all(row['output'][0]['rows'][0][1:]==['9223372036854775808','雪'] for row in result),result
        assert all(not row.get('error') and row['instance']['version'].split('-')[0]=='9.7.0' for row in result)
        checks.append('native-all-member-addresses-columns-exact-wide-text-and-Unicode')
        _value,result=run('SET GLOBAL max_connections='+str(target))
        assert len(result)==len(peers) and all(not row.get('error') for row in result),result
        assert all(maximum(peer)==target for peer in peers)
        other=next(peer for peer in peers if peer!=seed)
        other_ref={'server_id':registrations[other]['server_id']}
        run('SET GLOBAL max_connections='+str(target+1),'all',{'exclude':[other_ref]})
        assert maximum(seed)==target+1 and maximum(other)==target
        run('SET GLOBAL max_connections='+str(target+2),'primary')
        assert maximum(seed)==target+2 and maximum(other)==target
        run('SET GLOBAL max_connections='+str(target+3),[other_ref])
        assert maximum(seed)==target+2 and maximum(other)==target+3
        checks.append('independent-native-local-global-setting-all-primary-explicit-and-registered-exclusion')
        before={peer:maximum(peer) for peer in peers}
        _value,result=run('SET GLOBAL max_connections='+str(target+4),'all',{'dryRun':True})
        assert len(result)==len(peers) and all('dry run execution' in row['warnings'] for row in result),result
        assert {peer:maximum(peer) for peer in peers}==before
        checks.append('native-dry-run-reports-targets-without-executing-SQL')
        value,result=run('SELECT * FROM mysql.sr_fanout_missing_table')
        assert value['native_operation_outcome']=='returned'
        assert len(result)==len(peers) and all(row['error']['code']==1146 for row in result),result
        checks.append('returned-native-method-retains-each-native-SQL-error')
        _value,result=run('SELECT SLEEP(3),@@server_uuid','all',{'timeout':1})
        assert len(result)==len(peers) and all(not row.get('error') and row['output'][0]['rows'][0][0]=='1' for row in result),result
        assert {row['output'][0]['rows'][0][1] for row in result}==expected,result
        checks.append('native-timeout-interrupts-SLEEP-and-retains-its-native-return-value')
        selected=options(context+'.execute',['SET GLOBAL max_connections='+str(target+5),'all'],seed)
        review=http('review',{'options':selected},peer=seed)
        before_metadata=http('inspect',peer=seed)['metadata']
        execute(context+'.set_routing_option',['stats_updates_frequency',
            {'cluster':17,'cluster_set':19,'replica_set':23}[context]],seed)
        assert http('inspect',peer=seed)['metadata']!=before_metadata,'Native metadata must actually change before asserting stale review refusal'
        http('start',{key:review[key] for key in ('job_id','review_digest')}|{'confirmed':True},peer=seed,refused=True)
        assert {peer:maximum(peer) for peer in peers}==before
        checks.append('changed-native-topology-metadata-refuses-stale-SQL-review-before-dispatch')
        from pgadmin.cdeadmin.workspace.mysql_topology_jobs import TopologyTransport
        original_execute=TopologyTransport.execute
        def lost_reply(self,*args,**kwargs):
            value=original_execute(self,*args,**kwargs)
            value['control']=None
            return value
        TopologyTransport.execute=lost_reply
        try:
            uncertain=execute(context+'.execute',['SELECT @@server_uuid','all'],seed,expect_returned=False)
        finally:TopologyTransport.execute=original_execute
        assert uncertain['state']=='unknown' and uncertain['server_recovery_clearance_required']
        observed=http('reconcile',{'job_id':uncertain['job_id']},peer=seed)
        clearance=observed['reconciliation']['server_recovery_quiescence']
        assert clearance['qualified'] is True and clearance['idle'] is True,clearance
        acknowledged=http('acknowledge',{'job_id':uncertain['job_id'],
            'target_confirmation':seeds[seed]['identity']['server_uuid'],
            'observation_digest':observed['observation_digest']},peer=seed)
        assert acknowledged['native_operation_outcome']=='unknown' and acknowledged['target_state_acknowledged_at']
        checks.append('lost-native-reply-keeps-unknown-outcome-through-independent-member-session-clearance-and-explicit-acknowledgement')
        return {'complete':True,'checks':checks,'native_instances':sorted(expected),
            'scope':'Native two-member topology SQL and independent per-server observations; arbitrary stored-program/asynchronous side effects and full HA traffic acceptance remain separate.'}
    finally:
        for peer,value in original.items():sql(peer,'SET GLOBAL max_connections=%s',(value,))
