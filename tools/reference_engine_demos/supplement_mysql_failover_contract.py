"""Admit fixed native failover calls only from matching pure/C and parser proof."""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]


def supplement(contract,evidence,artifact,digest,root):
    if contract.get('engine_id')!='mysql' or contract.get('reference_version')!='9.7.0' or not evidence.get('complete') or not evidence.get('owned_servers_stopped'):
        raise ValueError('Stopped native MySQL9.7 failover qualification is required')
    interfaces=evidence.get('interfaces',[])
    if len(interfaces)!=2 or {row.get('native_connection_class') for row in interfaces}!={'CharsetMySQLConnection','CharsetCMySQLConnection'}:
        raise ValueError('Both native connector implementations must qualify')
    ops={'add_failover_source','remove_failover_source','add_managed_failover','remove_managed_failover','reset_failover_sources'}
    for row in interfaces:
        if set(row.get('operations',[]))!=ops or not all(row.get(key) for key in ['native_effects','ddn_plan_apply_effects','stale_review_and_post_ack_loss','warnings_and_savepoint_preserved','native_latin1_conversion_3854_preserved']):
            raise ValueError('Native failover effects, failure and DDN proof are incomplete')
    if not evidence.get('parser',{}).get('library_sha256') or evidence['parser'].get('parser_version')!='9.7.0':
        raise ValueError('Native MySQL9.7 parser proof is required')
    if len(evidence.get('native_denials',[]))!=2 or not all(row.get('source_only_ddn_plan_apply') for row in evidence['native_denials']):
        raise ValueError('Independent native grants need qualification')
    for path,digest_value in evidence['source_sha256'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=digest_value:raise ValueError('Native failover source changed after qualification')
    value=deepcopy(contract);proofs=['mysql-9.7.0-failover-parser','mysql-9.7.0-failover-execution']
    ids={'visual_admin.'+('server' if op=='reset_failover_sources' else 'replication-channel')+'.'+op for op in ops}
    value['task_templates']=[row for row in value['task_templates'] if row['task_id'] not in ids]
    first=interfaces[0]['templates']
    for op in sorted(ops):
        sql=first[op]['source']
        if any(row['templates'][op]['source']!=sql for row in interfaces):raise ValueError('Native connector statement templates differ')
        value['task_templates'].append({'task_id':'visual_admin.'+('server' if op=='reset_failover_sources' else 'replication-channel')+'.'+op,
            'source':sql,'required_bindings':['parameter_'+str(n+1) for n in range(sql.count('%s'))],
            'binding_style':'pyformat_percent_s','proof_ids':proofs})
    value['task_templates'].sort(key=lambda row:row['task_id'])
    value['proof_records']=[row for row in value['proof_records'] if row['evidence_id'] not in proofs]+[
        {'evidence_id':key,'evidence_kind':kind,'authority':'Native MySQL9.7 Community asynchronous failover UDFs; pure/C native effects, DDN and scoped grant enforcement',
            'artifact':artifact,'sha256':digest,'format':'native failover qualification JSON','license_id':'PostgreSQL'}
        for key,kind in zip(proofs,['parser_acceptance','live_execution'])]
    value['live_evidence_ids']=sorted(set(value['live_evidence_ids'])|{proofs[1]})
    tasks=[row['task_id'] for row in value['task_templates']]
    value['coverage'].update(authoritative_task_ids=tasks,authoritative_task_count=len(tasks),implemented_task_count=len(tasks))
    return value


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',required=True,type=Path)
    parser.add_argument('--contract',type=Path,default=ROOT/'web/pgadmin/cdeadmin/providers/mysql_family/mysql_dialect_9_7_0.json')
    args=parser.parse_args();raw=args.evidence.read_bytes();value=supplement(json.loads(args.contract.read_text()),json.loads(raw),args.evidence.name,hashlib.sha256(raw).hexdigest(),ROOT)
    args.contract.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n')
