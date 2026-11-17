"""Notify the authoritative design store after a native catalog alias change."""
from copy import deepcopy


def require_binding_notice(workspace, context, database_target_id, result):
    if (not isinstance(result, dict) or result.get('action') != 'rename'
            or not (result.get('native_acknowledged') is True or (
                result.get('state') == 'unknown_outcome'
                and result.get('native_dispatched') is True))):
        return None
    return workspace.design_store.mark_native_catalog_bindings_suspect(
        engine='duckdb', endpoint_id=context.endpoint_id,
        database_target_id=database_target_id,
        event_key='duckdb-alias:' + result['review_id'],
        resource_ids=result.get('invalidate_resource_ids') or [
            row['resource_id'] for row in result['alias_review']['descendants']])


def record_binding_notice(workspace, context, database_target_id, result):
    if (not isinstance(result, dict) or result.get('action') != 'rename'
            or not (result.get('native_acknowledged') is True or (
                result.get('state') == 'unknown_outcome'
                and result.get('native_dispatched') is True))):
        return result
    if (result.get('binding_notice') or {}).get('status') == 'recorded':
        return result
    response = deepcopy(result)
    try:
        response['binding_notice'] = require_binding_notice(
            workspace, context, database_target_id, result)
    except Exception as error:
        response['binding_notice'] = {'status': 'unconfirmed',
            'error_type': type(error).__name__, 'native_retry': False}
    return response
