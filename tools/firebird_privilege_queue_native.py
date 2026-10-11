"""Native original-plan queue order, partial effects and single-use admission."""
import uuid
from types import SimpleNamespace


def qualify(connection, unused_provider, route, root):
    from pgadmin.cdeadmin.core import EndpointContext
    from pgadmin.cdeadmin.providers.firebird.provider import FirebirdProvider, PROFILE
    from pgadmin.cdeadmin.visual_admin.provider import VisualAdminError, VisualAdminExecutionError
    context = EndpointContext(
        endpoint_id=str(uuid.uuid4()), mode='legacy_native', experience_family='firebird',
        provider_id=PROFILE.provider_id, provider_version='0.1.0', profile_id=PROFILE.profile_id,
        profile_version=PROFILE.exact_version, runtime_verification_state='verified',
        verified_runtime_family='firebird', verified_runtime_version='5.0.4',
        target_adapter_id='firebird_wire-client', target_adapter_version='owned',
        pool_namespace=str(uuid.uuid4()), session_namespace=str(uuid.uuid4()),
        cache_namespace=str(uuid.uuid4()), diagnostic_namespace=str(uuid.uuid4()),
        effective_permissions=frozenset({'network', 'secret_read', 'data_read', 'data_write', 'administer', 'execute'}))
    provider = FirebirdProvider(context, SimpleNamespace(require=lambda *_: None), unused_provider.client)
    def sql(source):
        with connection.cursor() as cursor:
            cursor.execute(source)
            return cursor.fetchall() if cursor.description else []
    sql('CREATE TABLE Q_PRIV (ID INTEGER)')
    sql('CREATE ROLE Q_ROLE')
    connection.commit()
    target = {'resource_kind': 'table', 'resource_id': 'table:Q_PRIV',
              'display_name': 'Q_PRIV', 'display_path': ['Q_PRIV']}
    def plan(operation, privilege, principal='Q_ROLE'):
        draft = {'principal_kind': 'ROLE', 'principal': principal, 'privileges': [privilege]}
        if operation == 'revoke': draft['confirmation'] = principal
        result = provider.plan_visual_admin({'_provider_route': route,
            'resource_kind': 'table', 'operation_id': operation, 'target_resource': target, 'draft': draft})
        assert result['state'] == 'ready', result
        return result
    def apply(value):
        return provider.apply_visual_admin({'plan_id': value['plan_id'],
            'plan_digest': value['plan_digest'], 'confirmed': True})
    def observed():
        if connection.main_transaction.is_active(): connection.rollback()
        result = sql("SELECT TRIM(RDB$PRIVILEGE) FROM RDB$USER_PRIVILEGES WHERE RDB$RELATION_NAME='Q_PRIV' AND RDB$USER='Q_ROLE' ORDER BY 1")
        connection.rollback()
        return result
    ordered = [plan('grant', 'SELECT'), plan('grant', 'UPDATE'), plan('revoke', 'SELECT')]
    receipts = [apply(value) for value in ordered]
    assert all(value['provider_result']['accepted'] for value in receipts)
    assert observed() == [('U',)]
    for value in ordered:
        try: apply(value)
        except VisualAdminError: pass
        else: raise AssertionError('Consumed privilege plan replayed')
    partial = [plan('grant', 'SELECT'), plan('grant', 'DELETE', 'Q_MISSING_ROLE'), plan('revoke', 'UPDATE')]
    apply(partial[0])
    try: apply(partial[1])
    except VisualAdminExecutionError: pass
    else: raise AssertionError('Missing native role unexpectedly accepted')
    # Mirrors queue stop: the last plan is never submitted after a failed middle item.
    assert observed() == [('S',), ('U',)]
    return {'ordered_original_plans': True, 'native_partial_effects_observed': True,
            'single_use_plans': True, 'unattempted_last_plan': True}
