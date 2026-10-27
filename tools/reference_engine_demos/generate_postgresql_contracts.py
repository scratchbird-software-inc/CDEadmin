"""Generate exact PostgreSQL contracts from native inventories and task receipts."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .generate_postgresql_dialect_inventory import sha256


def evidence(evidence_id,kind,authority,artifact,digest,format_name,license_id='PostgreSQL'):
    return {'evidence_id':evidence_id,'evidence_kind':kind,'authority':authority,'artifact':artifact,
            'sha256':digest,'format':format_name,'license_id':license_id}


def generate(dialect_inventory,metrics_inventory,native_receipt,metrics_receipt,root):
    from pgadmin.cdeadmin.providers.postgresql.contracts import PROFILE,dialect_task_ids
    from pgadmin.cdeadmin.providers.postgresql.preserved_surface import adapt_catalog
    from pgadmin.cdeadmin.engine_contracts import validate_dialect_contract,validate_metrics_contract
    dialect_inventory,metrics_inventory,native_receipt,metrics_receipt=map(Path,(dialect_inventory,metrics_inventory,native_receipt,metrics_receipt))
    root=Path(root);di=json.loads(dialect_inventory.read_text());mi=json.loads(metrics_inventory.read_text());live=json.loads(native_receipt.read_text())
    metric_live=json.loads(metrics_receipt.read_text())
    if metric_live.get('complete') is not True or metric_live.get('inventory_sha256')!=sha256(metrics_inventory):
        raise ValueError('Native PostgreSQL metrics execution evidence differs')
    if not live.get('complete') or live.get('failures'):raise ValueError('Native PostgreSQL task gate is incomplete')
    if di.get('inventory_id')!='postgresql.dialect-inventory.18.3.v1' or mi.get('inventory_id')!='postgresql.metrics-inventory.18.3.v1':
        raise ValueError('Exact PostgreSQL inventory identities differ')
    for name in ('runtime_catalogs_exhausted','grammar_files_exhausted'):
        if di['completeness'].get(name) is not True:raise ValueError('Native PostgreSQL grammar inventory is incomplete')
    if mi['completeness'].get('source_views_exhausted') is not True:raise ValueError('Native PostgreSQL metrics inventory is incomplete')
    proofs={}
    for row in live.get('native_admin_task_proofs',[]):
        task='postgresql.'+row['task_id'].replace(':','.')
        if row.get('native_execution_returned') is True and row.get('transaction_outcome')=='committed':proofs.setdefault(task,[]).append(row)
    expected=set(dialect_task_ids())
    if set(proofs)!=expected:raise ValueError('Native SQL compiler task evidence differs: '+str(sorted(expected^set(proofs))))
    identity={'provider_id':PROFILE.provider_id,'profile_id':PROFILE.profile_id,'engine_id':PROFILE.engine_id,
              'reference_version':PROFILE.exact_version,'interface_id':'libpq-psycopg3'}
    grammar=evidence('postgresql18.3-source','grammar','PostgreSQL18.3 source',di['source_evidence']['archive'],
        di['source_evidence']['archive_sha256'],'PostgreSQL18.3 source archive')
    catalog=evidence('postgresql18.3-catalog','catalog','PostgreSQL18.3 native catalog',dialect_inventory.name,sha256(dialect_inventory),di['schema'])
    parser=evidence('postgresql18.3-task-parser','parser_acceptance','PostgreSQL18.3 native parser',native_receipt.name,sha256(native_receipt),
        'native SQL execution receipts; successful execution requires native parsing')
    execution=evidence('postgresql18.3-task-execution','live_execution','PostgreSQL18.3 native execution',native_receipt.name,sha256(native_receipt),
        'native SQL compiler task receipts')
    forms={}
    for obj in adapt_catalog({'objects':[]})['objects']:
        for operation in obj['operations']:
            task='postgresql.'+obj['resource_kind']+'.'+operation['operation_id']
            if task in expected:forms[task]=operation
    if set(forms)!=expected:raise ValueError('Native PostgreSQL task form bindings differ')
    compiler_paths=['web/pgadmin/cdeadmin/providers/postgresql/'+name for name in ('native_admin.py','large_objects.py','preserved_surface.py')]
    compiler_sources={name:sha256(root/name) for name in compiler_paths}
    if any(live.get('source_sha256',{}).get(name)!=digest for name,digest in compiler_sources.items()):
        raise ValueError('Native PostgreSQL task receipts belong to different compiler sources')
    templates=[]
    for task in sorted(expected):
        kind,operation=task.split('.',2)[1:];definition=forms[task]
        required=[field['field_id'] for field in definition['form']['fields'] if field.get('required')]
        if definition.get('target_required'):required.append('target_resource')
        statements=sorted({row.get('statement_sha256') or hashlib.sha256(row['statement'].encode('utf8')).hexdigest() for row in proofs[task]})
        templates.append({'task_id':task,'source':'pgadmin.cdeadmin.providers.postgresql.native_admin.compile_native_admin:'+kind+':'+operation,
            'source_format':'provider_native_compiler_reference','required_bindings':required,
            'native_statement_sha256s':statements,'native_execution_count':len(proofs[task]),
            'proof_ids':[parser['evidence_id'],execution['evidence_id']]})
    inventories={name:[{**deepcopy(row),'proof_ids':[grammar['evidence_id'] if name in {'statements','commands','diagnostics'} or row.get('lexical_kind') or row.get('language_profile')=='postgresql-plpgsql' else catalog['evidence_id']]} for row in entries]
                 for name,entries in di['inventories'].items()}
    counts={name:len(entries) for name,entries in inventories.items()}
    if counts!=di['completeness']['inventory_counts']:raise ValueError('Native PostgreSQL inventory counts differ')
    decisions={
        'identifier_quoting':'Native unquoted folding; exact double-quoted identifiers with doubled quote escapes.',
        'string_literals':'Native observed standard_conforming_strings and escape/unicode/dollar string forms; no global editor mode override.',
        'parameter_binding':'libpq extended-query numbered parameters; client named/positional pyformat binding is separate from native SQL text.',
        'transaction_control':'Native PostgreSQL transaction authority; retained editor transactions and independently owned administration attachments.',
        'pagination':'Native LIMIT/OFFSET and FETCH; provider cursor pages preserve native row and type identity.',
        'explain':'Native EXPLAIN; ANALYZE executes the selected statement and is separate from nonexecuting syntax checks.',
        'cancellation':'Native owned libpq cancellation key; acknowledgement is separate from native transaction finality.'}
    dialect={**identity,'schema':'cdeadmin.engine-dialect.v2','contract_id':'postgresql.dialect.18.3.v1',
        'language_profiles':['postgresql-sql','postgresql-plpgsql'],'grammar_evidence':grammar,
        'proof_records':[grammar,catalog,parser,execution],'inventories':inventories,
        'complete_grammar_inventory':{'artifact':dialect_inventory.name,'sha256':sha256(dialect_inventory),**di['completeness']},
        'syntax_decisions':{name:{'syntax':description,'proof_ids':[grammar['evidence_id'],execution['evidence_id']]} for name,description in decisions.items()},
        'task_templates':templates,'compiler_sources':compiler_sources,
        'coverage':{'scope':'cdeadmin_generated_tasks','language_acceptance_authority':'engine_parser','authoritative_inventory_counts':counts,
            'authoritative_task_ids':sorted(expected),'authoritative_task_count':len(expected),'implemented_task_count':len(expected),
            'qualification_scope':'Provider SQL compiler tasks only. Preserved HTTP forms, physical-tool jobs, platform qualification and full-product completion retain separate acceptance.'},
        'live_evidence_ids':[execution['evidence_id']]}
    metric_proof=evidence('postgresql18.3-metric-catalog','catalog','PostgreSQL18.3 source and native catalog',metrics_inventory.name,
        sha256(metrics_inventory),mi['schema'])
    metric_execution=evidence('postgresql18.3-metric-execution','live_execution','PostgreSQL18.3 native statistics functions',metrics_receipt.name,
        sha256(metrics_receipt),'Native privileged/restricted read-only collector observations')
    observations=[];metrics=[]
    for endpoint in mi['endpoints']:
        for column in endpoint['columns']:
            observation_id='postgresql.'+endpoint['endpoint_id']+'.'+column['name']
            observations.append({'observation_id':observation_id,'native_name':endpoint['source']+'.'+column['name'],
                'scope':endpoint['scope'],'source':endpoint['native_query'],'value_type':column['value_type'],
                'observation_class':'native_metric' if column.get('metric') else 'native_state_or_dimension',
                'description':'Native PostgreSQL '+endpoint['endpoint_id']+' column '+column['name'],
                'privilege':'Native view/function privileges and statistics visibility; denied families are explicit.',
                'version_condition':'PostgreSQL18.3 core view shape of the observed installation.',
                'collection_cost':'Owned read-only collector; selected families only; bounded rows, row bytes and native statement timeout.',
                'poll_interval_seconds':15,'cardinality':'Native view row dimensions; collector-session sources do not observe user editor sessions.',
                'redaction':column['redaction'],'evidence_ids':[metric_proof['evidence_id'],metric_execution['evidence_id']]})
            if column.get('metric'):
                metrics.append({'metric_id':observation_id,'observation_id':observation_id,**column['metric'],'evidence_ids':[metric_proof['evidence_id'],metric_execution['evidence_id']]})
    metric_contract={**identity,'schema':'cdeadmin.engine-metrics.v2','contract_id':'postgresql.metrics.18.3.v1',
        'catalog_evidence':metric_proof,'classification_evidence':[metric_proof,metric_execution],
        'native_observations':observations,'metrics':metrics,
        'authoritative_observation_ids':[row['observation_id'] for row in observations],'authoritative_observation_count':len(observations),
        'authoritative_metric_ids':[row['metric_id'] for row in metrics],'authoritative_metric_count':len(metrics),
        'live_evidence_ids':[metric_execution['evidence_id']],
        'coverage':mi['completeness']}
    validate_dialect_contract(dialect,PROFILE,dialect_task_ids());validate_metrics_contract(metric_contract,PROFILE)
    return dialect,metric_contract
