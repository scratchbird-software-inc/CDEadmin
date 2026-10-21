"""Source facts exclude prose/actions and preserve native type aliases."""
import pytest
from reference_engine_demos.mysql_source_inventory import Grammar,command_inventory,type_inventory


def test_bison_first_alternative_comments_raw_actions_and_optional_rule_terminators():
    source='''/* Note: prose is not a rule. */
%%
simple_statement:
    first { const char *s=R"tag(fake_rule: | ; {})tag"; if (true) { s="| ;"; } }
  | second
;
first: FIRST_SYM
second: SECOND_SYM { char c='\\''; }
'''
    value=Grammar(source)
    assert set(value.rules)=={'simple_statement','first','second'}
    rows=value.alternatives('simple_statement','statements')
    assert [row['native_name'] for row in rows]==['first','second']
    assert rows[0]['source']=='sql/sql_yacc.yy:4'


def test_native_dispatch_inventory_is_not_a_list_of_grammar_helpers_or_comments():
    source='''// SQLCOM_COMMENTED is not a command.
enum enum_sql_command { SQLCOM_SELECT=0, /* SQLCOM_FAKE */ SQLCOM_CREATE_TABLE, SQLCOM_END };'''
    rows=command_inventory(source)
    assert [row['native_name'] for row in rows]==['SQLCOM_SELECT','SQLCOM_CREATE_TABLE']
    assert all(row['inventory_kind']=='native-dispatch-id' for row in rows)


def test_type_inventory_expands_real_keyword_aliases_and_optional_precision():
    grammar=Grammar('''%%
type: int_type field_length | real_type | varchar field_length;
int_type: INT_SYM;
real_type: DOUBLE_SYM opt_PRECISION;
opt_PRECISION: %empty | PRECISION;
varchar: CHAR_SYM VARYING | VARCHAR_SYM;
''')
    lexical='''static const SYMBOL symbols[] = {
    {SYM("INT", INT_SYM)}, {SYM("INTEGER", INT_SYM)},
    {SYM("DOUBLE", DOUBLE_SYM)}, {SYM("PRECISION", PRECISION)},
    {SYM("CHAR", CHAR_SYM)}, {SYM("CHARACTER", CHAR_SYM)},
    {SYM("VARYING", VARYING)}, {SYM("VARCHAR", VARCHAR_SYM)}};
    '''
    assert [row['native_name'] for row in type_inventory(grammar,lexical)]==[
        'CHAR VARYING','CHARACTER VARYING','DOUBLE','DOUBLE PRECISION','INT','INTEGER','VARCHAR']


def test_unrecognized_native_type_heads_fail_instead_of_silently_claiming_coverage():
    grammar=Grammar('%%\ntype: newly_added_type;\n')
    with pytest.raises(ValueError,match='Unrecognized native type head'):
        type_inventory(grammar,'static const SYMBOL symbols[] = {{SYM("INT",INT_SYM)}};')
