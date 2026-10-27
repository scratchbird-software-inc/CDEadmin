"""Register SDI import only after stopped, source-bound native pure/C proof."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def supplement(contract,evidence,artifact,sha,source_root):
    if (contract.get('engine_id')!='mysql' or contract.get('reference_version')!='9.7.0' or
            evidence.get('complete') is not True or evidence.get('owned_server_stopped') is not True):
        raise ValueError('Select completed stopped native MySQL9.7 SDI evidence')
    interfaces=evidence.get('interfaces',[])
    if len(interfaces)!=2 or {row.get('use_pure') for row in interfaces}!={True,False}:
        raise ValueError('Both native connector paths must qualify SDI import')
    for row in interfaces:
        if (row.get('native_connection_class')!=('CharsetMySQLConnection' if row['use_pure'] else 'CharsetCMySQLConnection') or
                any(row.get(key) is not True for key in ('native_import_returned','full_native_rows_and_definition_verified',
                    'changed_review_refused','missing_file_native_error_preserved','server_host_filename_unicode_and_apostrophe_preserved'))):
            raise ValueError('The native SDI effect and failure evidence is incomplete')
    for path in ('mysql_instance.py','administration.py','provider.py'):
        relative=Path('web/pgadmin/cdeadmin/providers/mysql_family')/path
        if evidence.get('source_sha256',{}).get(str(relative))!=hashlib.sha256((source_root/relative).read_bytes()).hexdigest():
            raise ValueError('The native SDI production source changed after qualification')
    value=deepcopy(contract);task='visual_admin.server.import_table_sdi';proofs=['mysql-9.7.0-sdi-parser','mysql-9.7.0-sdi-execution']
    value['task_templates']=[row for row in value['task_templates'] if row['task_id']!=task]+[{
        'task_id':task,'source':'IMPORT TABLE FROM %s','source_format':'ordered_native_statements',
        'statements':['IMPORT TABLE FROM %s'],'required_bindings':['parameter_1'],'binding_style':'pyformat_percent_s','proof_ids':proofs}]
    value['task_templates'].sort(key=lambda row:row['task_id'])
    value['proof_records']=[row for row in value['proof_records'] if row['evidence_id'] not in proofs]+[{
        'evidence_id':key,'evidence_kind':kind,'authority':'Native MySQL9.7 Community SDI import; actual MyISAM files and pure/C clients',
        'artifact':artifact,'sha256':sha,'format':'owned SDI import qualification JSON','license_id':'PostgreSQL'}
        for key,kind in zip(proofs,('parser_acceptance','live_execution'))]
    value['live_evidence_ids']=sorted(set(value['live_evidence_ids'])|{proofs[1]})
    tasks=[row['task_id'] for row in value['task_templates']]
    value['coverage'].update(authoritative_task_ids=tasks,authoritative_task_count=len(tasks),implemented_task_count=len(tasks))
    return value


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',required=True,type=Path)
    parser.add_argument('--contract',type=Path,default=ROOT/'web/pgadmin/cdeadmin/providers/mysql_family/mysql_dialect_9_7_0.json')
    args=parser.parse_args();raw=args.evidence.read_bytes()
    value=supplement(json.loads(args.contract.read_text()),json.loads(raw),args.evidence.name,hashlib.sha256(raw).hexdigest(),ROOT)
    args.contract.write_text(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n')
