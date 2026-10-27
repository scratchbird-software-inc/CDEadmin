"""Admit native SHUTDOWN/RESTART templates from actual pure/C process proof."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OPERATIONS={'shutdown_server':'SHUTDOWN','restart_server':'RESTART'}
PROOFS=['mysql-9.7.0-server-control-parser','mysql-9.7.0-server-control-execution']


def supplement(contract,evidence,artifact,digest,source_root):
    if not evidence.get('complete') or not evidence.get('owned_server_stopped') or not evidence.get('owned_container_removed'):
        raise ValueError('Completed stopped native server-control evidence is required')
    interfaces=evidence.get('interfaces',[])
    if len(interfaces)!=2 or {row.get('use_pure') for row in interfaces}!={True,False}:raise ValueError('Both native driver interfaces are required')
    for row in interfaces:
        if (row.get('native_connection_class')!=('CharsetMySQLConnection' if row['use_pure'] else 'CharsetCMySQLConnection') or
                row.get('templates')!=OPERATIONS or {c.get('operation') for c in row.get('checks',[])}!=set(OPERATIONS)):
            raise ValueError('Native request and external process checks are incomplete')
    if {(row['use_pure'],row['native_errno']) for row in evidence.get('native_refusals',[])}!={(True,1227),(False,1227),(True,3707),(False,3707)}:
        raise ValueError('Actual native privilege and unmanaged-server refusals are required')
    required={'web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in ('mysql_server_control.py','administration.py','provider.py')}
    if not required<=set(evidence.get('source_sha256',{})):raise ValueError('Native source fingerprints are required')
    for name,value in evidence['source_sha256'].items():
        path=Path(name)
        if path.is_absolute() or '..' in path.parts or hashlib.sha256((source_root/path).read_bytes()).hexdigest()!=value:raise ValueError('Native server-control source differs: '+name)
    result=deepcopy(contract)
    if result.get('engine_id')!='mysql' or result.get('reference_version')!='9.7.0':raise ValueError('Select native MySQL9.7.0')
    ids={'visual_admin.server.'+operation for operation in OPERATIONS}
    result['task_templates']=[row for row in result['task_templates'] if row['task_id'] not in ids]
    for operation,source in OPERATIONS.items():
        result['task_templates'].append({'task_id':'visual_admin.server.'+operation,'source':source,'source_format':'ordered_native_statements',
            'statements':[source],'required_bindings':[],'binding_style':'pyformat_percent_s','proof_ids':PROOFS})
    result['task_templates'].sort(key=lambda row:row['task_id'])
    result['proof_records']=[row for row in result['proof_records'] if row['evidence_id'] not in PROOFS]
    for proof,kind in zip(PROOFS,('parser_acceptance','live_execution')):
        result['proof_records'].append({'evidence_id':proof,'evidence_kind':kind,'authority':'Actual native MySQL9.7 pure/C requests with independent owned supervisor/process/data observations',
            'artifact':artifact,'sha256':digest,'format':'owned native server-control qualification JSON','license_id':'PostgreSQL'})
    result['live_evidence_ids']=sorted(set(result['live_evidence_ids'])|{PROOFS[1]})
    tasks=[row['task_id'] for row in result['task_templates']];result['coverage'].update(authoritative_task_ids=tasks,authoritative_task_count=len(tasks),implemented_task_count=len(tasks))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',required=True,type=Path)
    parser.add_argument('--contract',type=Path,default=ROOT/'web/pgadmin/cdeadmin/providers/mysql_family/mysql_dialect_9_7_0.json')
    args=parser.parse_args();raw=args.evidence.read_bytes()
    result=supplement(json.loads(args.contract.read_text()),json.loads(raw),args.evidence.name,hashlib.sha256(raw).hexdigest(),ROOT)
    args.contract.write_text(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n')
