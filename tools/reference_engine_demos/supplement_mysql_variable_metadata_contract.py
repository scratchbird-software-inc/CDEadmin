"""Attach additional native variable evidence without adding declared tasks."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PROOFS=['mysql-9.7.0-variable-metadata-parser','mysql-9.7.0-variable-metadata-execution']
TASKS={'visual_admin.system-variable.'+op for op in ('set_global','set_persist','set_persist_only','reset_persist')}


def supplement(contract,evidence,artifact,digest,source_root):
    if not evidence.get('complete') or not evidence.get('core_complete') or not evidence.get('owned_server_stopped'):
        raise ValueError('Completed stopped native variable qualification is required')
    interfaces=evidence.get('interfaces',[])
    if len(interfaces)!=2 or {r.get('use_pure') for r in interfaces}!={True,False}:raise ValueError('Both native drivers are required')
    for row in interfaces:
        if row.get('native_connection_class')!=('CharsetMySQLConnection' if row['use_pure'] else 'CharsetCMySQLConnection'):raise ValueError('Wrong native driver')
        checks={r['scope']:r for r in row['checks']}
        if not checks['native-metadata-and-navigation']['all_native_rows_reconciled'] or not checks['native-ddn-null-rediscovery']['explicit_native_is_null']:
            raise ValueError('Native metadata and NULL observation are required')
        for name in ('private-completion-default-mode','private-completion-ANSI_QUOTES,NO_BACKSLASH_ESCAPES'):
            check=checks[name]
            for field in ('native_statement_counters','native_error_area_statement_counters'):
                before,after=check[field]
                if not before>0 or before!=after:raise ValueError('Nonzero independent source statement counters must stay unchanged')
            if not all(check.get(flag) for flag in ('row_count_preserved','error_area_preserved','pending_savepoint_preserved')):raise ValueError('Native diagnostics/pending work changed')
        if set(row['templates'])!={'set_global','set_persist','set_persist_only','reset_persist'}:raise ValueError('Variable assignment scopes are incomplete')
    if not evidence.get('source_sha256'):raise ValueError('Native source fingerprints are required')
    for name,value in evidence['source_sha256'].items():
        path=Path(name)
        if path.is_absolute() or '..' in path.parts or hashlib.sha256((source_root/path).read_bytes()).hexdigest()!=value:
            raise ValueError('Native variable source differs: '+name)
    result=deepcopy(contract)
    if result.get('engine_id')!='mysql' or result.get('reference_version')!='9.7.0':raise ValueError('Select MySQL9.7.0')
    found=set()
    for task in result['task_templates']:
        if task['task_id'] in TASKS:
            task['proof_ids']=list(dict.fromkeys(task['proof_ids']+PROOFS));found.add(task['task_id'])
    if found!=TASKS:raise ValueError('Existing native variable tasks are missing')
    result['proof_records']=[r for r in result['proof_records'] if r['evidence_id'] not in PROOFS]
    for proof,kind in zip(PROOFS,('parser_acceptance','live_execution')):
        result['proof_records'].append({'evidence_id':proof,'evidence_kind':kind,
            'authority':'Actual native MySQL9.7 metadata/catalog, typed DOUBLE/NULL and persistence, explicit runtime NULL DDN rediscovery, independent pure/C source counters/diagnostics and native accepted variable-completion SQL',
            'artifact':artifact,'sha256':digest,'format':'native variable qualification JSON','license_id':'PostgreSQL'})
    result['live_evidence_ids']=sorted(set(result['live_evidence_ids'])|{PROOFS[1]})
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',required=True,type=Path)
    parser.add_argument('--contract',type=Path,default=ROOT/'web/pgadmin/cdeadmin/providers/mysql_family/mysql_dialect_9_7_0.json')
    args=parser.parse_args();raw=args.evidence.read_bytes()
    result=supplement(json.loads(args.contract.read_text()),json.loads(raw),args.evidence.name,hashlib.sha256(raw).hexdigest(),ROOT)
    args.contract.write_text(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n')
