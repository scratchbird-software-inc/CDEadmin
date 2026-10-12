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
