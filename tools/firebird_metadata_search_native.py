"""Search native catalog names, comments, source and column metadata."""


def qualify(connection, other=None):
    from pgadmin.cdeadmin.providers.firebird.provider import _resources
    from pgadmin.cdeadmin.workspace.firebird_search import search
    with connection.cursor() as cursor:
        cursor.execute('CREATE TABLE SEARCH_NATIVE (SEARCH_FIELD INTEGER)')
        cursor.execute("COMMENT ON TABLE SEARCH_NATIVE IS 'Needle Comment 世界'")
        cursor.execute('CREATE PROCEDURE SEARCH_PROC RETURNS (V INTEGER) AS BEGIN SELECT COUNT(*) FROM SEARCH_NATIVE INTO V; SUSPEND; END')
    connection.commit()
    snapshot = {'generation': 'native-search', 'resources': _resources(connection, {})}
    connection.rollback()
    checks = {}
    for name, query, fields, kind in [
            ('names', 'search_native', {'name'}, 'table'),
            ('comments', 'needle comment 世界', {'description'}, 'table'),
            ('source', 'search_native', {'source'}, 'procedure'),
            ('columns', 'search_field', {'name'}, 'column')]:
        result = search(snapshot, query, fields, kind)
        assert result['match_count'] > 0, (name, result)
        checks[name] = {'count': result['match_count'], 'ids': [item['resource_id'] for item in result['matches']]}
    assert search(snapshot, 'x.*; DROP TABLE SEARCH_NATIVE', {'source', 'name'})['match_count'] == 0
    isolated = None
    if other is not None:
        with other.cursor() as cursor:
            cursor.execute('CREATE TABLE SEARCH_NATIVE (OTHER_FIELD INTEGER)')
        other.commit()
        with other.cursor() as cursor:
            cursor.execute("COMMENT ON TABLE SEARCH_NATIVE IS 'Other database only'")
        other.commit()
        independent = {'generation': 'independent-native-search', 'resources': _resources(other, {})}
        other.rollback()
        assert search(independent, 'needle comment 世界', {'description'})['match_count'] == 0
        assert search(independent, 'search_field', {'fields'})['match_count'] == 0
        assert search(independent, 'other_field', {'fields'}, 'table')['match_count'] > 0
        assert search(snapshot, 'other_field', {'fields'})['match_count'] == 0
        isolated = True
    return {'passed': True, 'native_checks': checks, 'literal_query_not_executed': True,
            'independent_database_catalogs_isolated': isolated}
