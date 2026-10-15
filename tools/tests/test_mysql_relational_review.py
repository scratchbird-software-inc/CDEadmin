"""Graphical field edits preserve native clauses and use ordinary scoped review."""
from copy import deepcopy
import pytest
from pgadmin.cdeadmin.workspace.mysql_relational_fields import edit_clause, datatype, merge_fields


def test_column_field_edits_preserve_defaults_generated_expressions_and_native_attributes():
    clause="`note` varchar(80) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL DEFAULT 'semi;,)NULL' COMMENT 'native' /*!80023 INVISIBLE */"
    result=edit_clause(clause,{'datatype':'varchar(120)','nullable':True,'description':"owner's \\ note"},'NO_BACKSLASH_ESCAPES')
    assert "varchar(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL DEFAULT 'semi;,)NULL'" in result
    assert "COMMENT 'owner''s \\ note' /*!80023 INVISIBLE */" in result
    generated='`computed` int GENERATED ALWAYS AS ((coalesce(`id`, NULL) + 1)) STORED'
    assert edit_clause(generated,{'nullable':False},'')==generated+' NOT NULL'
    assert edit_clause("`x` int DEFAULT NULL",{'nullable':False},'')=="`x` int DEFAULT NULL NOT NULL"


def test_native_type_edits_reject_statements_and_attributes_but_keep_enum_literals():
    assert datatype("enum('a;b', 'c,)')",'NO_BACKSLASH_ESCAPES')=="enum('a;b', 'c,)')"
    assert datatype('bigint unsigned','')=='bigint unsigned'
    for value in ['int; DROP TABLE t','int DEFAULT 4','varchar(20) COMMENT \'x\'','unknown',"enum('unclosed)"]:
        with pytest.raises(ValueError):datatype(value,'')


def test_conflicting_native_and_graphical_edits_and_new_field_identity_are_refused():
    uid='mysql:ep:db:table';column_uid=uid+':"id"'
    fields={column_uid:{'datatype':'int','_label':'id','_property_names':['uid','datatype']}}
    before={'uid':uid,'name':'t','kind':'table','native':{'database':'db','definition':'CREATE TABLE `t` (`id` int)'},'fields':fields}
    desired=deepcopy(before);desired['fields'][column_uid]['datatype']='bigint'
    result=merge_fields(before,desired,'');assert '`id` bigint' in result['definition']
    desired['native']['definition']='CREATE TABLE `t` (`id` smallint)'
    with pytest.raises(ValueError,match='disagree'):merge_fields(before,desired,'')
    desired=deepcopy(before);desired['fields']['new']={'datatype':'int','_label':'new'}
    with pytest.raises(ValueError,match='reconciliation'):merge_fields(before,desired,'')
    desired=deepcopy(before);desired['fields']={}
    assert merge_fields(before,desired,'')==before['native']


def test_explicit_new_graphical_columns_preserve_native_clauses_and_do_not_remove_omissions():
    uid='mysql:ep:db:table'
    before={'uid':uid,'name':'t','kind':'table','native':{'database':'db',
        'definition':"CREATE TABLE `t` (`id` int NOT NULL DEFAULT 42, PRIMARY KEY (`id`)) ENGINE=InnoDB"},
        'fields':{uid+':"id"':{'datatype':'int','_label':'id','_property_names':['uid','datatype']}}}
    desired=deepcopy(before)
    desired['fields']={'new-field':{'datatype':'varchar(80)','nullable':True,'description':"owner's note",'_label':'n`é',
                                  '_property_names':['uid','datatype','nullable','description']}}
    with pytest.raises(ValueError,match='reconciliation'):merge_fields(before,desired,'')
    result=merge_fields(before,desired,'',allow_new_columns=True)
    assert "`id` int NOT NULL DEFAULT 42, PRIMARY KEY (`id`)" in result['definition']
    assert "`n``é` varchar(80) NULL COMMENT 'owner''s note'" in result['definition']
    assert result['definition'].endswith('ENGINE=InnoDB')
    from pgadmin.cdeadmin.workspace.mysql_schema_plan import alteration
    source=alteration({'name':'t','native':before['native']},{'name':'t','native':result},'')
    assert source.startswith('ALTER TABLE `db`.`t` ADD COLUMN `n``é`') and 'DROP' not in source


@pytest.mark.parametrize('new_field', [
    {'_label':'id','datatype':'int'}, {'_label':'n','datatype':'int DEFAULT 1'},
    {'_label':'n'}, {'_label':'n','datatype':'int','nullable':'true'},
    {'_label':'x'*65,'datatype':'int'}, {'_label':'n','datatype':'int','_property_names':['default']},
])
def test_new_graphical_column_admission_refuses_rebinding_and_unsupported_attributes(new_field):
    before={'uid':'table','name':'t','kind':'table','native':{'database':'db','definition':'CREATE TABLE `t` (`id` int)'},'fields':{}}
    desired=deepcopy(before);desired['fields']={'new':new_field}
    with pytest.raises(ValueError):merge_fields(before,desired,'',allow_new_columns=True)


def test_graphical_addition_cannot_override_conflicting_native_new_column():
    before={'uid':'table','name':'t','kind':'table','native':{'database':'db','definition':'CREATE TABLE `t` (`id` int)'},'fields':{}}
    desired=deepcopy(before);desired['native']['definition']='CREATE TABLE `t` (`id` int, `n` bigint)'
    desired['fields']={'new':{'_label':'n','datatype':'int'}}
    with pytest.raises(ValueError,match='disagree'):merge_fields(before,desired,'',allow_new_columns=True)


def test_host_new_column_option_requires_boolean_and_preserves_target_admission(monkeypatch):
    from unittest.mock import Mock
    from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService, ProviderWorkspaceError
    from pgadmin.cdeadmin.workspace import firebird_relational_review
    service=object.__new__(ProviderWorkspaceService)
    service.mysql_catalog=Mock(return_value={'snapshot': 'authorized catalog'})
    handoff=Mock(return_value={'status':'prepared-for-native-preview'})
    monkeypatch.setattr(firebird_relational_review,'handoff',handoff)
    base={'database_target_id':'target','original':'before','snapshot':'after'}
    for value in ('true', 1, None, {}):
        with pytest.raises(ProviderWorkspaceError):
            service.mysql_relational_review('server',{**base,'allow_new_columns':value})
    service.mysql_catalog.assert_not_called()
    result=service.mysql_relational_review('server',{**base,'allow_new_columns':True})
    service.mysql_catalog.assert_called_once_with('server',{'database_target_id':'target'})
    handoff.assert_called_once_with('authorized catalog','before','after',engine='mysql',allow_new_columns=True,allow_column_renames=False,allow_foreign_keys=False)
    assert result['status']=='prepared-for-native-preview'


def test_graphical_rename_uses_stable_uid_and_reconciles_native_references_without_touching_literals():
    uid='mysql:ep:db:table';field=uid+':"note"'
    before={'uid':uid,'name':'t','kind':'table','native':{'database':'db',
        'definition':"CREATE TABLE `t` (`note` varchar(80) NOT NULL DEFAULT 'note', `g` int GENERATED ALWAYS AS (length(`note`)) STORED, KEY `note` (`note`(10)), CONSTRAINT `c` CHECK ((`note` <> 'note'))) ENGINE=InnoDB"},
        'fields':{field:{'_label':'note','datatype':'varchar(80)','_property_names':['uid','datatype']}}}
    desired=deepcopy(before);desired['fields'][field]['_label']='memo`é'
    with pytest.raises(ValueError,match='reconciliation'):merge_fields(before,desired,'')
    result=merge_fields(before,desired,'',allow_column_renames=True)
    assert result['mysql_change']=={'rename_columns':{'note':'memo`é'}}
    assert "DEFAULT 'note'" in result['definition'] and "<> 'note'" in result['definition']
    assert 'KEY `note` (`memo``é`(10))' in result['definition']
    assert 'length(`memo``é`)' in result['definition']
    from pgadmin.cdeadmin.workspace.mysql_schema_plan import alteration
    assert 'CHANGE COLUMN `note` `memo``é`' in alteration({'name':'t','native':before['native']},{'name':'t','native':result},'')


def test_graphical_rename_preserves_other_table_foreign_key_targets_and_updates_self_references():
    uid='table';field=uid+':"id"'
    before={'uid':uid,'name':'t','kind':'table','native':{'database':'db','definition':
        'CREATE TABLE `t` (`id` int, CONSTRAINT `external` FOREIGN KEY (`id`) REFERENCES `other` (`id`), CONSTRAINT `self` FOREIGN KEY (`id`) REFERENCES `t` (`id`))'},
        'fields':{field:{'_label':'id','datatype':'int'}}}
    desired=deepcopy(before);desired['fields'][field]['_label']='new_id'
    result=merge_fields(before,desired,'',allow_column_renames=True)
    assert 'FOREIGN KEY (`new_id`) REFERENCES `other` (`id`)' in result['definition']
    assert 'FOREIGN KEY (`new_id`) REFERENCES `t` (`new_id`)' in result['definition']
    desired['native']['definition']=desired['native']['definition'].replace('int','bigint')
    with pytest.raises(ValueError,match='simultaneous native edits'):merge_fields(before,desired,'',allow_column_renames=True)


def test_graphical_native_relationship_changes_cannot_disappear_from_review(monkeypatch):
    from pgadmin.cdeadmin.workspace import firebird_relational_review as review
    from unittest.mock import Mock
    owner={'uid':'mysql:ep:target:table','native':{},'native_json':'{}','graphical_relationships':[
        {'uid':'foreign-key','source':'table','target':'parent','kind':'ref','enforcement':'database','native_json':'[]'}]}
    original={'table':owner}
    changed=deepcopy(original);changed['table']['graphical_relationships'][0]['target']='other'
    monkeypatch.setattr(review,'read_catalog',Mock(return_value={'rows':{}}))
    monkeypatch.setattr(review,'read_relations',Mock(side_effect=[original,changed]))
    with pytest.raises(ValueError,match='foreign-key reconciliation'):
        review.handoff({}, {}, {}, engine='mysql')


def test_native_relationship_reader_captures_stable_endpoints_but_labels_are_presentation():
    from pgadmin.cdeadmin.workspace.firebird_relational_review import read_relations
    import json
    source='ddn "0.6"; module "scratchrobin.mysql.relations"; data relations {'
    for name in ('source','target'):
        source+='object '+name+' '+json.dumps(name)+' {kind:table;uid:"mysql:ep:target:'+name+'";x_record:{resource_id:"'+name+'",native_json:"{}"};}'
    source+='relation fk "display label" @source -> @target {kind:ref;enforcement:database;uid:"fk";x_record:{native_json:"[]"};}} view v {data:[@relations];projection {kind:graph;profile:"ddn@1";}}'
    snapshot={'format':'ddn-workspace@1','entry':'relations.ddn','view':'v','files':{'relations.ddn':source}}
    result=read_relations(snapshot,engine='mysql')
    edges=next(row['graphical_relationships'] for row in result.values() if 'graphical_relationships' in row)
    assert edges==[{'uid':'fk','kind':'ref','enforcement':'database','native_json':'[]','source':'source','target':'target'}]
    snapshot['files']['relations.ddn']=source.replace('display label','new presentation label')
    updated=read_relations(snapshot,engine='mysql')
    assert next(row['graphical_relationships'] for row in updated.values() if 'graphical_relationships' in row)==edges
