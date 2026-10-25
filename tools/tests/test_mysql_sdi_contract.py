"""SDI task admission requires both identified native effects and current code."""
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest
from reference_engine_demos.supplement_mysql_sdi_contract import supplement


def proof():
    root=Path(__file__).resolve().parents[2]
    value={'complete':True,'owned_server_stopped':True,'source_sha256':{},'interfaces':[]}
    for name in ('mysql_instance.py','administration.py','provider.py'):
        path=Path('web/pgadmin/cdeadmin/providers/mysql_family')/name
        value['source_sha256'][str(path)]=hashlib.sha256((root/path).read_bytes()).hexdigest()
    for pure in (True,False):
        value['interfaces'].append({'use_pure':pure,'native_connection_class':'CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection',
            **{key:True for key in ('native_import_returned','full_native_rows_and_definition_verified','changed_review_refused',
                'missing_file_native_error_preserved','server_host_filename_unicode_and_apostrophe_preserved')}})
    contract={'engine_id':'mysql','reference_version':'9.7.0','task_templates':[],'proof_records':[],'live_evidence_ids':[],'coverage':{}}
    return root,contract,value


@pytest.mark.parametrize('failure',['not-stopped','one-interface','wrong-class','no-data-effect','changed-source'])
def test_incomplete_native_sdi_proof_cannot_expand_the_admitted_task_contract(failure):
    root,contract,evidence=proof()
    if failure=='not-stopped':evidence['owned_server_stopped']=False
    if failure=='one-interface':evidence['interfaces'].pop()
    if failure=='wrong-class':evidence['interfaces'][1]['native_connection_class']='simulated'
    if failure=='no-data-effect':evidence['interfaces'][0]['full_native_rows_and_definition_verified']=False
    if failure=='changed-source':evidence['source_sha256'][next(iter(evidence['source_sha256']))]='0'*64
    with pytest.raises(ValueError):supplement(contract,evidence,'native.json','a'*64,root)


def test_sdi_task_admission_is_idempotent_and_does_not_infer_product_completion():
    root,contract,evidence=proof();before=deepcopy(contract)
    result=supplement(contract,evidence,'native.json','a'*64,root)
    assert contract==before and result==supplement(result,evidence,'native.json','a'*64,root)
    assert result['coverage']['implemented_task_count']==1
    assert result['task_templates'][0]['required_bindings']==['parameter_1']
    assert 'full_product_complete' not in result
