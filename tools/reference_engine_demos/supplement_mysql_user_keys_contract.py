"""Admit user-key tasks only from stopped, source-matched native pure/C proof."""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
STATEMENTS={
    'install_user_key_functions':['INSTALL PLUGIN keyring_udf SONAME %s']+[
        'CREATE FUNCTION '+name+' RETURNS '+result+' SONAME %s' for name,result in
        [('keyring_key_store','INTEGER'),('keyring_key_fetch','STRING'),('keyring_key_type_fetch','STRING'),
         ('keyring_key_length_fetch','INTEGER'),('keyring_key_remove','INTEGER'),('keyring_key_generate','INTEGER')]],
    'inspect_user_key':['SELECT keyring_key_type_fetch(%s),keyring_key_length_fetch(%s)'],
    'store_user_key':['SELECT keyring_key_store(%s,%s,%s)'],
    'generate_user_key':['SELECT keyring_key_generate(%s,%s,%s)'],
    'remove_user_key':['SELECT keyring_key_remove(%s)']}


def supplement(contract,evidence,artifact,digest,root):
    if (contract.get('engine_id')!='mysql' or contract.get('reference_version')!='9.7.0' or
            evidence.get('complete') is not True or evidence.get('owned_server_stopped') is not True or
            evidence.get('native_principal_ownership_verified') is not True):
        raise ValueError('Completed, stopped native MySQL9.7 user-key and principal-ownership proof is required')
    interfaces=evidence.get('interfaces',[])
    if len(interfaces)!=2 or {row.get('native_connection_class') for row in interfaces}!={'CharsetMySQLConnection','CharsetCMySQLConnection'}:
        raise ValueError('Both native connector implementations must qualify')
    required={'reviewed-native-plugin-and-six-UDF-registration-with-existing-definitions-preserved','exact-UTF8-store-native-generation-inspection-and-removal',
        'stale-key-fingerprint-refused-before-dispatch','post-native-ack-observation-loss-keeps-ACK-and-never-replays','no-key-material-in-preview-or-receipt'}
    for row in interfaces:
        if row.get('complete') is not True or row.get('native_functions_verified')!=6 or not required<=set(row.get('checks',[])):
            raise ValueError('Native key effects and failure evidence are incomplete')
    for name in ['mysql_user_keys.py','administration.py','provider.py']:
        relative=Path('web/pgadmin/cdeadmin/providers/mysql_family')/name
        if evidence.get('source_sha256',{}).get(str(relative))!=hashlib.sha256((root/relative).read_bytes()).hexdigest():
            raise ValueError('Native user-key production source changed after qualification')
    value=deepcopy(contract);proofs=['mysql-9.7.0-user-key-parser','mysql-9.7.0-user-key-execution']
    identifiers={'visual_admin.server.'+name for name in STATEMENTS}
    value['task_templates']=[row for row in value['task_templates'] if row['task_id'] not in identifiers]
    for name,statements in STATEMENTS.items():
        value['task_templates'].append({'task_id':'visual_admin.server.'+name,'source':';\n'.join(statements),
            'source_format':'ordered_native_statements','statements':statements,
            'required_bindings':['parameter_'+str(i+1) for i in range(sum(s.count('%s') for s in statements))],
            'binding_style':'pyformat_percent_s','proof_ids':proofs})
    value['task_templates'].sort(key=lambda row:row['task_id'])
    value['proof_records']=[row for row in value['proof_records'] if row['evidence_id'] not in proofs]+[
        {'evidence_id':key,'evidence_kind':kind,'authority':'Native Community keyring_udf with active GPL file keyring, actual pure/C effects and principal isolation',
            'artifact':artifact,'sha256':digest,'format':'owned native user-key qualification JSON','license_id':'PostgreSQL'}
        for key,kind in zip(proofs,['parser_acceptance','live_execution'])]
    value['live_evidence_ids']=sorted(set(value['live_evidence_ids'])|{proofs[1]})
    tasks=[row['task_id'] for row in value['task_templates']]
    value['coverage'].update(authoritative_task_ids=tasks,authoritative_task_count=len(tasks),implemented_task_count=len(tasks))
    return value


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--contract',type=Path,default=ROOT/'web/pgadmin/cdeadmin/providers/mysql_family/mysql_dialect_9_7_0.json')
    args=parser.parse_args();raw=args.evidence.read_bytes()
    value=supplement(json.loads(args.contract.read_text()),json.loads(raw),args.evidence.name,hashlib.sha256(raw).hexdigest(),ROOT)
    args.contract.write_text(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n')
