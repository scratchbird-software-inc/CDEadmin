"""Admit selected-prefix native cache tasks from completed pure/C proof."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OPERATIONS={'inspect_key_cache':'SELECT @@GLOBAL.','configure_key_cache':'SET GLOBAL ','release_key_cache':'SET GLOBAL '}
PROOFS=['mysql-9.7.0-key-cache-lifecycle-parser','mysql-9.7.0-key-cache-lifecycle-execution']


def supplement(contract,evidence,artifact,digest,source_root):
    if not evidence.get('complete') or evidence.get('owned_server_stopped') is not True:raise ValueError('Completed stopped native evidence is required')
    interfaces=evidence.get('interfaces',[])
    if len(interfaces)!=2 or {row['use_pure'] for row in interfaces}!={True,False}:raise ValueError('Both native interfaces are required')
    for row in interfaces:
        if row['native_connection_class']!=('CharsetMySQLConnection' if row['use_pure'] else 'CharsetCMySQLConnection') or set(row.get('templates',{}))!=set(OPERATIONS) or len(row.get('checks',[]))<7:
            raise ValueError('Native cache lifecycle receipts are incomplete')
    if interfaces[0]['templates']!=interfaces[1]['templates']:raise ValueError('Native generated templates differ')
    paths=evidence.get('source_sha256',{})
    required={'web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in ('mysql_key_cache_lifecycle.py','administration.py','provider.py','mysql_charsets.py','mysql_warnings.py')}
    if not required<=set(paths):raise ValueError('Native production source fingerprints are required')
    for path,value in paths.items():
        relative=Path(path)
        if relative.is_absolute() or '..' in relative.parts or hashlib.sha256((source_root/relative).read_bytes()).hexdigest()!=value:raise ValueError('Native source differs: '+path)
    result=deepcopy(contract)
    if result.get('engine_id')!='mysql' or result.get('reference_version')!='9.7.0':raise ValueError('Select MySQL9.7.0')
    ids={'visual_admin.server.'+operation for operation in OPERATIONS}
    result['task_templates']=[row for row in result['task_templates'] if row['task_id'] not in ids]
    for operation,prefix in OPERATIONS.items():
        source=interfaces[0]['templates'][operation]
        if not isinstance(source,str) or not source.startswith(prefix) or source.count('%s')!=(0 if operation=='inspect_key_cache' else 1):raise ValueError('Generated native cache statement differs')
        result['task_templates'].append({'task_id':'visual_admin.server.'+operation,'source':source,
            'source_format':'ordered_native_statements','statements':[source],'required_bindings':[] if operation=='inspect_key_cache' else ['parameter_1'],
            'binding_style':'pyformat_percent_s','proof_ids':PROOFS})
    result['task_templates'].sort(key=lambda row:row['task_id'])
    result['proof_records']=[row for row in result['proof_records'] if row['evidence_id'] not in PROOFS]
    for proof,kind in zip(PROOFS,('parser_acceptance','live_execution')):
        result['proof_records'].append({'evidence_id':proof,'evidence_kind':kind,'authority':'Native MySQL9.7 Community; independently identified pure/C cache workflows',
            'artifact':artifact,'sha256':digest,'format':'owned native key-cache lifecycle qualification JSON','license_id':'PostgreSQL'})
    result['live_evidence_ids']=sorted(set(result['live_evidence_ids'])|{PROOFS[1]})
    tasks=[row['task_id'] for row in result['task_templates']];result['coverage'].update(authoritative_task_ids=tasks,authoritative_task_count=len(tasks),implemented_task_count=len(tasks))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',required=True,type=Path)
    parser.add_argument('--contract',type=Path,default=ROOT/'web/pgadmin/cdeadmin/providers/mysql_family/mysql_dialect_9_7_0.json')
    args=parser.parse_args();raw=args.evidence.read_bytes()
    result=supplement(json.loads(args.contract.read_text()),json.loads(raw),args.evidence.name,hashlib.sha256(raw).hexdigest(),ROOT)
    args.contract.write_text(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n')
