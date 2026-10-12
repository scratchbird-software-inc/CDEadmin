"""Native DDN UDF declaration round trips; never invoke uninstalled libraries."""
from copy import deepcopy
import json
from pgadmin.cdeadmin.providers.firebird import external_functions as udf
from pgadmin.cdeadmin.providers.firebird.schema_application import capture, apply_review
from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan, digest
from pgadmin.cdeadmin.workspace.firebird_schema_apply import SchemaApplications
from pgadmin.cdeadmin.workspace.firebird_external_function_plan import FIELDS, DERIVED


def qualify(connection, provider, route, root):
    definitions = []
    for kind in udf.TYPES:
        item = {'data_type': kind}
        if kind in ('CHAR', 'VARCHAR', 'NCHAR', 'NCHAR VARYING', 'BINARY', 'VARBINARY', 'CSTRING'):
            item['length'] = 32
        if kind in ('NUMERIC', 'DECIMAL'): item.update(precision=38, scale=12)
        definitions.append({'arguments': [item]})
    definitions.extend([
        {'arguments': [{'data_type': 'CSTRING', 'length': 32, 'character_set': 'UTF8'}]},
        {'arguments': [{'data_type': 'TIME', 'time_zone': 'WITH TIME ZONE'}]},
        {'arguments': [{'data_type': 'TIMESTAMP', 'time_zone': 'WITH TIME ZONE'}]},
        *({'arguments': [{'data_type': 'INTEGER', 'mechanism': mechanism}]} for mechanism in udf.INPUT_MECHANISMS),
        *({'return_mechanism': mechanism} for mechanism in udf.RETURN_MECHANISMS),
        {'return_data_type': 'BLOB', 'return_mechanism': 'REFERENCE'},
        {'arguments': [{'data_type': 'INTEGER', 'mechanism': 'DESCRIPTOR'}],
         'return_mode': 'PARAMETER', 'return_parameter': 1,
         'return_data_type': None, 'return_mechanism': None},
    ])
    for index, definition in enumerate(definitions):
        draft = {'name': 'SOURCE_' + str(index), 'arguments': [{'data_type': 'INTEGER'}],
            'return_data_type': 'INTEGER', 'return_mechanism': 'VALUE',
            'entrypoint': 'not_invoked', 'module_name': 'not_installed', **definition}
        for statement in udf.compile_operation('create', draft): connection.execute_immediate(statement)
    connection.commit()
    target = {'endpoint_id': 'owned', 'database_target_id': 'owned', 'generation': 'udf-plan'}
    def snapshot():
        if connection.main_transaction.is_active(): connection.rollback()
        value = capture(connection, target); connection.rollback(); return value
    store = SchemaApplications(root / 'udf-review-receipts.json')
    def apply(base, desired):
        desired['sha256'] = digest(desired['rows'])
        plan = build_plan(base, desired, base)
        if plan['status'] != 'review-ready':
            (root / 'udf-plan-blockers.json').write_text(json.dumps(plan['blockers'], indent=2))
        assert plan['status'] == 'review-ready', plan['blockers']
        review = store.review(plan, base, desired, 'owner', 'binding', route['database'])
        result = store.apply({'review_id': review['review_id'], 'review_digest': review['review_digest'],
            'confirmed': True}, 'owner', 'binding', lambda record: apply_review(provider, route, record))['outcome']
        assert result['native_commit_returned'] and result['attachment_released'], result
        assert result['rediscovery']['available'] and all(item['matches_reviewed_properties']
            for item in result['rediscovery']['objects']), result
        return result
    base = snapshot(); desired = deepcopy(base)
    for index in range(len(definitions)):
        original = base['rows']['external-function:SOURCE_' + str(index)]
        name = 'COPY_' + str(index); identity = 'external-function:' + name
        desired['rows'][identity] = {**deepcopy(original), 'resource_id': identity,
            'name': name, 'path': [name], 'native': {key: value for key, value in
                original['native'].items() if key in FIELDS | DERIVED}}
    apply(base, desired)
    live = snapshot()
    for index in range(len(definitions)):
        left, right = (live['rows']['external-function:' + prefix + str(index)]['native']
                       for prefix in ('SOURCE_', 'COPY_'))
        assert all(left[key] == right[key] for key in ('parameters', 'return_argument', 'module_name', 'entrypoint'))
    base = live; desired = deepcopy(base)
    desired['rows']['external-function:COPY_0']['native'].update(
        module_name='new_uninstalled_library', entrypoint='other_not_invoked', description="review's comment")
    apply(base, desired)
    return {'native_signature_roundtrips': len(definitions), 'binding_and_comment_rediscovered': True,
            'native_abi_invoked': False, 'library_installed': False, 'owned_transaction_released': True}
