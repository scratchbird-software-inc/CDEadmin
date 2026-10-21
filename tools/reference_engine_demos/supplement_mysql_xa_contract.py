"""Admit native prepared XA tasks from completed identified pure/C receipts."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
OPERATIONS={'inspect_prepared_xa':'XA RECOVER CONVERT XID','commit_prepared_xa':'XA COMMIT ','rollback_prepared_xa':'XA ROLLBACK '}
PROOFS=['mysql-9.7.0-prepared-xa-parser','mysql-9.7.0-prepared-xa-execution']


def supplement(contract,evidence,artifact,digest,source_root):
    if not evidence.get('complete') or evidence.get('owned_server_stopped') is not True:raise ValueError('Completed stopped native XA evidence is required')
    interfaces=evidence.get('interfaces',[])
    if len(interfaces)!=2 or {row['use_pure'] for row in interfaces}!={True,False}:raise ValueError('Both native XA interfaces are required')
    for row in interfaces:
        if row['native_connection_class']!=('CharsetMySQLConnection' if row['use_pure'] else 'CharsetCMySQLConnection') or set(row.get('templates',{}))!=set(OPERATIONS) or len(row.get('checks',[]))<8:
            raise ValueError('Native XA receipts are incomplete')
        for operation,prefix in OPERATIONS.items():
            source=row['templates'][operation]
            if operation=='inspect_prepared_xa':valid=source==prefix
            else:valid=isinstance(source,str) and source.startswith(prefix) and re.fullmatch(r"X'(?:[0-9A-F]{2}){0,64}',X'(?:[0-9A-F]{2}){0,64}',[0-9]{1,19}",source[len(prefix):])
            if not valid:raise ValueError('Native XA generated statement differs')
    paths=evidence.get('source_sha256',{})
    required={'web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in ('mysql_xa.py','mysql_server_catalog.py','administration.py','provider.py')}
    if not required<=set(paths):raise ValueError('Native XA source fingerprints are required')
    for path,value in paths.items():
        relative=Path(path)
        if relative.is_absolute() or '..' in relative.parts or hashlib.sha256((source_root/relative).read_bytes()).hexdigest()!=value:raise ValueError('Native XA source differs: '+path)
    result=deepcopy(contract)
    if result.get('engine_id')!='mysql' or result.get('reference_version')!='9.7.0':raise ValueError('Select MySQL9.7.0')
    ids={'visual_admin.server.'+operation for operation in OPERATIONS}
    result['task_templates']=[row for row in result['task_templates'] if row['task_id'] not in ids]
    for operation in OPERATIONS:
        source=interfaces[0]['templates'][operation]
        result['task_templates'].append({'task_id':'visual_admin.server.'+operation,'source':source,
            'source_format':'ordered_native_statements','statements':[source],'required_bindings':[],
            'binding_style':'pyformat_percent_s','proof_ids':PROOFS})
    result['task_templates'].sort(key=lambda row:row['task_id'])
    result['proof_records']=[row for row in result['proof_records'] if row['evidence_id'] not in PROOFS]
    for proof,kind in zip(PROOFS,('parser_acceptance','live_execution')):
        result['proof_records'].append({'evidence_id':proof,'evidence_kind':kind,'authority':'Native MySQL9.7 Community; independently identified pure/C prepared XA workflows',
            'artifact':artifact,'sha256':digest,'format':'owned native prepared XA qualification JSON','license_id':'PostgreSQL'})
    result['live_evidence_ids']=sorted(set(result['live_evidence_ids'])|{PROOFS[1]})
    tasks=[row['task_id'] for row in result['task_templates']];result['coverage'].update(authoritative_task_ids=tasks,authoritative_task_count=len(tasks),implemented_task_count=len(tasks))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',required=True,type=Path)
    parser.add_argument('--contract',type=Path,default=ROOT/'web/pgadmin/cdeadmin/providers/mysql_family/mysql_dialect_9_7_0.json')
    args=parser.parse_args();raw=args.evidence.read_bytes()
    result=supplement(json.loads(args.contract.read_text()),json.loads(raw),args.evidence.name,hashlib.sha256(raw).hexdigest(),ROOT)
    args.contract.write_text(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n')
