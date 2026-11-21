"""Identity and executable-task boundary for native PostgreSQL contracts."""
from dataclasses import dataclass

from .native_admin import POSTGRESQL_ADMIN_OPERATIONS,POSTGRESQL_NATIVE_FORM_KINDS


@dataclass(frozen=True)
class PostgreSQLContractProfile:
    provider_id:str='org.pgadmin.postgresql'
    profile_id:str='postgresql-native'
    engine_id:str='postgresql'
    exact_version:str='18.3'
    language_profile:str='postgresql-sql'
    dialect_contract_file:str='postgresql_dialect_18_3.json'
    metrics_contract_file:str='postgresql_metrics_18_3.json'


PROFILE=PostgreSQLContractProfile()


def dialect_task_ids():
    # Preserved pgAdmin HTTP/form workflows retain their own qualification.
    # This contract covers the exact executable provider-native SQL compiler set.
    from .preserved_surface import adapt_catalog
    return tuple(sorted(
        f"postgresql.{obj['resource_kind']}.{operation['operation_id']}"
        for obj in adapt_catalog({'objects': []})['objects']
        for operation in obj['operations']
        if operation.get('execution_route') == 'provider-native'
    ))
