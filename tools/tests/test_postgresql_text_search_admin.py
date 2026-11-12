"""PostgreSQL text search configuration, dictionary, parser and template
create/alter/drop compile to exact native statements (M5)."""
import pytest
from pgadmin.cdeadmin.providers.postgresql.native_admin import (
    compile_native_admin, PostgreSQLNativeAdminError,
)
from pgadmin.cdeadmin.providers.postgresql.text_search import facts, form

NATIVES = {
    'text-search-configuration': {
        'schema': 'service', 'name': 'c1', 'comment': None,
        'catalog_row': {'cfgname': 'c1', 'cfgparser': '3722'},
        'children': {'pg_ts_config_map': [{'maptokentype': 1}]}},
    'text-search-dictionary': {
        'schema': 'service', 'name': 'd1', 'comment': 'd',
        'catalog_row': {'dictname': 'd1', 'dicttemplate': '3727',
                        'dictinitoption': "stopwords = 'english'"}},
    'text-search-parser': {
        'schema': 'service', 'name': 'p1', 'comment': None,
        'catalog_row': {'prsname': 'p1', 'prsstart': 'prsd_start',
                        'prstoken': 'prsd_nexttoken', 'prsend': 'prsd_end',
                        'prslextype': 'prsd_lextype', 'prsheadline': '-'}},
    'text-search-template': {
        'schema': 'service', 'name': 't1', 'comment': None,
        'catalog_row': {'tmplname': 't1', 'tmplinit': 'dsimple_init',
                        'tmpllexize': 'dsimple_lexize'}},
}


def compile_kind(kind, operation, draft):
    native = dict(NATIVES[kind], text_search_facts=facts(kind, NATIVES[kind]))
    return compile_native_admin({
        'resource_kind': kind, 'operation_id': operation, 'draft': draft,
        'target_resource': {'extensions': {'postgresql': {'native': native}}}})


def statements(kind, operation, draft):
    return compile_kind(kind, operation, draft)['statement'].split(';\n')


def test_facts_read_the_captured_rows():
    assert facts('text-search-parser', NATIVES['text-search-parser'])[
        'prsheadline'] is None
    assert facts('text-search-dictionary', NATIVES['text-search-dictionary'])[
        'dictinitoption'] == "stopwords = 'english'"
    assert facts('text-search-configuration',
                 NATIVES['text-search-configuration'])['mapping_count'] == 1


def test_configuration_lifecycle():
    assert statements('text-search-configuration', 'create', {
        'name': 'c one', 'schema': 'Sch ema',
        'copy_config': 'pg_catalog.english',
        'tokens': [{'token': 'asciiword',
                    'dictname': 'service.d1, english_stem'}],
        'owner': 'dba', 'description': "it's"}) == [
        'CREATE TEXT SEARCH CONFIGURATION "Sch ema"."c one" (COPY = '
        'pg_catalog.english)',
        'ALTER TEXT SEARCH CONFIGURATION "Sch ema"."c one" ADD MAPPING FOR '
        'asciiword WITH service.d1, english_stem',
        'ALTER TEXT SEARCH CONFIGURATION "Sch ema"."c one" OWNER TO "dba"',
        'COMMENT ON TEXT SEARCH CONFIGURATION "Sch ema"."c one" IS '
        "'it''s'"]
    assert statements('text-search-configuration', 'create', {
        'name': 'c', 'schema': 's', 'prsname': 'pg_catalog.default'}) == [
        'CREATE TEXT SEARCH CONFIGURATION "s"."c" (PARSER = '
        'pg_catalog.default)']
    with pytest.raises(PostgreSQLNativeAdminError, match='not both'):
        compile_kind('text-search-configuration', 'create', {
            'name': 'c', 'schema': 's', 'prsname': 'x', 'copy_config': 'y'})
    assert statements('text-search-configuration', 'alter', {
        'name': 'c2', 'schema': 'archive', 'owner': 'dba', 'description': 'x',
        'add_mappings': [{'token': 'email', 'dictname': 'simple'}],
        'alter_mappings': [{'token': 'asciiword', 'dictname': 'english_stem'}],
        'drop_mappings': [{'token': 'url'}]}) == [
        'ALTER TEXT SEARCH CONFIGURATION "service"."c1" ADD MAPPING FOR email '
        'WITH simple',
        'ALTER TEXT SEARCH CONFIGURATION "service"."c1" ALTER MAPPING FOR '
        'asciiword WITH english_stem',
        'ALTER TEXT SEARCH CONFIGURATION "service"."c1" DROP MAPPING FOR url',
        'ALTER TEXT SEARCH CONFIGURATION "service"."c1" OWNER TO "dba"',
        'COMMENT ON TEXT SEARCH CONFIGURATION "service"."c1" IS \'x\'',
        'ALTER TEXT SEARCH CONFIGURATION "service"."c1" RENAME TO "c2"',
        'ALTER TEXT SEARCH CONFIGURATION "service"."c2" SET SCHEMA "archive"']
    with pytest.raises(PostgreSQLNativeAdminError, match='token type'):
        compile_kind('text-search-configuration', 'alter', {
            'drop_mappings': [{'token': 'a b'}]})
    assert statements('text-search-configuration', 'drop', {
        'confirmation': 'c1', 'cascade': True}) == [
        'DROP TEXT SEARCH CONFIGURATION "service"."c1" CASCADE']


def test_dictionary_lifecycle():
    assert statements('text-search-dictionary', 'create', {
        'name': 'd one', 'schema': 's', 'template': 'pg_catalog.simple',
        'options': [{'option': 'stopwords', 'value': 'english'},
                    {'option': 'accept', 'value': "it's"}],
        'owner': 'dba', 'description': 'c'}) == [
        'CREATE TEXT SEARCH DICTIONARY "s"."d one" (TEMPLATE = '
        "pg_catalog.simple, stopwords = 'english', accept = 'it''s')",
        'ALTER TEXT SEARCH DICTIONARY "s"."d one" OWNER TO "dba"',
        'COMMENT ON TEXT SEARCH DICTIONARY "s"."d one" IS \'c\'']
    assert statements('text-search-dictionary', 'alter', {
        'set_options': [{'option': 'accept', 'value': 'false'}],
        'drop_options': [{'option': 'stopwords'}], 'description': ''}) == [
        'ALTER TEXT SEARCH DICTIONARY "service"."d1" (accept = \'false\', '
        'stopwords)',
        'COMMENT ON TEXT SEARCH DICTIONARY "service"."d1" IS NULL']
    with pytest.raises(PostgreSQLNativeAdminError, match='template is fixed'):
        compile_kind('text-search-dictionary', 'alter', {'template': 'x'})
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_kind('text-search-dictionary', 'alter', {'name': 'd1'})


def test_parser_and_template_lifecycles():
    assert statements('text-search-parser', 'create', {
        'name': 'p', 'schema': 's', 'prsstart': 'prsd_start',
        'prstoken': 'prsd_nexttoken', 'prsend': 'prsd_end',
        'prslextype': 'prsd_lextype', 'description': 'c'}) == [
        'CREATE TEXT SEARCH PARSER "s"."p" (START = prsd_start, GETTOKEN = '
        'prsd_nexttoken, END = prsd_end, LEXTYPES = prsd_lextype)',
        'COMMENT ON TEXT SEARCH PARSER "s"."p" IS \'c\'']
    with pytest.raises(PostgreSQLNativeAdminError,
                       match='LEXTYPES is required'):
        compile_kind('text-search-parser', 'create', {
            'name': 'p', 'schema': 's', 'prsstart': 'a', 'prstoken': 'b',
            'prsend': 'c'})
    # A changed function drops and recreates with the merged definition.
    assert statements('text-search-parser', 'alter', {
        'prsheadline': 'prsd_headline', 'name': 'p2'}) == [
        'DROP TEXT SEARCH PARSER "service"."p1"',
        'CREATE TEXT SEARCH PARSER "service"."p1" (START = prsd_start, '
        'GETTOKEN = prsd_nexttoken, END = prsd_end, LEXTYPES = prsd_lextype, '
        'HEADLINE = prsd_headline)',
        'ALTER TEXT SEARCH PARSER "service"."p1" RENAME TO "p2"']
    assert statements('text-search-template', 'create', {
        'name': 't', 'schema': 's', 'tmpllexize': 'dsimple_lexize'}) == [
        'CREATE TEXT SEARCH TEMPLATE "s"."t" (LEXIZE = dsimple_lexize)']
    assert statements('text-search-template', 'alter', {
        'schema': 'archive', 'description': 'd'}) == [
        'COMMENT ON TEXT SEARCH TEMPLATE "service"."t1" IS \'d\'',
        'ALTER TEXT SEARCH TEMPLATE "service"."t1" SET SCHEMA "archive"']
    assert statements('text-search-template', 'drop', {'confirmation': 't1'}) \
        == ['DROP TEXT SEARCH TEMPLATE "service"."t1" RESTRICT']


def test_forms_and_routes():
    def field(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    create = {f['field_id']: f for f in form(
        'text-search-parser', 'create', field)['fields']}
    assert create['prslextype']['required'] and not create['prsheadline'][
        'required']
    alter = {f['field_id']: f for f in form(
        'text-search-configuration', 'alter', field)['fields']}
    assert {'add_mappings', 'alter_mappings', 'drop_mappings'} <= set(alter)
    assert 'owner' not in {f['field_id'] for f in form(
        'text-search-template', 'alter', field)['fields']}
    from pgadmin.cdeadmin.providers.postgresql.preserved_surface import (
        adapt_catalog)
    catalog = adapt_catalog({'objects': []})
    for kind in NATIVES:
        resource = next(item for item in catalog['objects']
                        if item['resource_kind'] == kind)
        routes = {op['operation_id']: op['execution_route']
                  for op in resource['operations']}
        assert routes['create'] == routes['alter'] == routes['drop'] == \
            'provider-native', kind
        assert routes['inspect'] == 'legacy-preserved', kind
