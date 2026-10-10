"""OpenSearch SQL/PPL 3.6.0 language provider."""

from pgadmin.cdeadmin.sdk import ActualEnginePilotProvider, PilotProfile

from .driver import OpenSearchSQLPPLDriver, OpenSearchSQLPPLDriverBackend


PROFILE = PilotProfile(
    provider_id='org.cdeadmin.opensearch_sql_ppl',
    profile_id='opensearch-sql-ppl',
    engine_id='opensearch_sql_ppl',
    engine_name='OpenSearch SQL/PPL',
    exact_version='3.6.0-sql-ppl',
    protocol_id='http_json',
    model_family='search-relational-analytic',
    language_profile='opensearch-sql-ppl',
    language_name='OpenSearch SQL and PPL',
    transaction_model='opensearch-query-request-native-outcome',
    result_kind='columnar',
    resource_kinds=(
        'catalog', 'data-source', 'query', 'saved-query',
        'prepared-query', 'language-settings', 'index', 'mapping',
        'settings', 'alias', 'index-template', 'component-template',
        'ingest-pipeline', 'shard', 'reindex-operation', 'snapshot',
        'ingest-processor', 'query-profile', 'repository',
    ),
    admin_tools=('sql-ppl-api', 'datasource-admin'),
    required_permissions=('network', 'secret_read'),
    language_mime_type='application/vnd.opensearch.sql-ppl',
    result_renderer_kind='columnar',
    result_renderer_id='cdeadmin.result.columnar.grid',
    result_component_reference='cdeadmin/results/ColumnarView',
    result_records_field='rows',
    result_export_formats=('csv', 'json', 'jsonl'),
    result_worker_required=True,
)


class OpenSearchSQLPPLPilotProvider(ActualEnginePilotProvider):
    language_alternatives = (('opensearch-sql', 'OpenSearch SQL', 'text/x-sql'), ('opensearch-ppl', 'OpenSearch PPL', 'text/x-ppl'))
    language_routes = {'opensearch-sql': 'sql', 'opensearch-ppl': 'ppl'}

    def _discard_unverified_session(self, handle):
        self.client.close_session(handle)

    def __init__(self, context, permissions, client):
        super().__init__(context, permissions, client, PROFILE)


def create_provider(context, permissions, client=None):
    return OpenSearchSQLPPLPilotProvider(
        context, permissions,
        client or OpenSearchSQLPPLDriver(
            PROFILE, OpenSearchSQLPPLDriverBackend(permissions.acquire_secret),
            OpenSearchSQLPPLDriverBackend.ADMIN_OPERATIONS),
    )
