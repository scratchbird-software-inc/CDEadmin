"""Refresh source-derived facts while retaining independently qualified tasks."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from reference_engine_demos.mysql_source_inventory import Grammar,command_inventory,type_inventory


def reconcile(contract,source_root):
    if contract.get('engine_id')!='mysql' or contract.get('reference_version')!='9.7.0':raise ValueError('Select the native MySQL9.7.0 contract')
    version=(source_root/'MYSQL_VERSION').read_text()
    for field,value in [('MYSQL_VERSION_MAJOR','9'),('MYSQL_VERSION_MINOR','7'),('MYSQL_VERSION_PATCH','0')]:
        if not any(line.strip()==field+'='+value for line in version.splitlines()):raise ValueError('Native MySQL source version differs')
    paths=['sql/sql_yacc.yy','sql/lex.h','include/my_sqlcommand.h']
    hashes={path:hashlib.sha256((source_root/path).read_bytes()).hexdigest() for path in paths}
    grammar=Grammar((source_root/paths[0]).read_text())
    source={'commands':command_inventory((source_root/paths[2]).read_text()),
        'statements':grammar.alternatives('simple_statement','statements'),
        'data_types':type_inventory(grammar,(source_root/paths[1]).read_text())}
    result=deepcopy(contract);proof='mysql-9.7.0-source-spelling-reconciliation'
    for group,rows in source.items():result['inventories'][group]=[{**row,'proof_ids':[proof]} for row in rows]
    result['proof_records']=[row for row in result['proof_records'] if row['evidence_id']!=proof]
    counts={name:len(rows) for name,rows in result['inventories'].items()}
    manifest={'reference_version':'9.7.0','source_sha256':hashes,'grammar_production_count':len(grammar.rules),
        'inventory_counts':counts,'inventory_sha256':{name:hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest() for name,rows in result['inventories'].items()},
        'native_dispatch_sentinel_excluded':'SQLCOM_END','source_packet_status':'structurally_complete_not_release_proven',
        'scope':'Native enum IDs, grammar entry alternatives and lexical SQL type spellings; source presence does not assert runtime availability or complete product support.'}
    digest=hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    result['source_inventory_reconciliation']=manifest
    result['proof_records'].append({'evidence_id':proof,'evidence_kind':'grammar','authority':'MySQL9.7.0 source grammar, lexical registry and native dispatch enum',
        'artifact':'embedded source_inventory_reconciliation','sha256':digest,'format':'source hashes and inventory scope JSON','license_id':'PostgreSQL'})
    result['coverage']['authoritative_inventory_counts']=counts
    previous=result['complete_grammar_inventory']
    prior=previous.get('prior_inventory_artifact') or {key:previous[key] for key in ('artifact','sha256')}
    result['complete_grammar_inventory'].update(artifact='embedded source_inventory_reconciliation',sha256=digest,
        prior_inventory_artifact=prior,inventory_counts=counts,
        grammar_productions_exhausted=False,source_inventory_reconciled=True,
        scope='Corrected source fact categories; runtime capabilities and wider product inventory remain independent.')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--contract',type=Path,default=ROOT/'web/pgadmin/cdeadmin/providers/mysql_family/mysql_dialect_9_7_0.json')
    args=parser.parse_args();value=reconcile(json.loads(args.contract.read_text()),args.source)
    args.contract.write_text(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n')
    print(json.dumps({group:len(value['inventories'][group]) for group in ('commands','statements','data_types')}))
