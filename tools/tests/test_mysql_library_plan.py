"""Library deployment never converts body edits into destructive replacement."""
from copy import deepcopy
import pytest
from pgadmin.cdeadmin.workspace.mysql_library_plan import compile_library


def row(comment="'initial'",body="$$ export function value() { return 'é'; } $$",mode=''):
    return {'name':'l`é','native':{'definition':'CREATE LIBRARY `l``é`\n COMMENT '+comment+'\n LANGUAGE JAVASCRIPT\n AS '+body,
        'definition_context':{'sql_mode':mode,'character_set_client':'utf8mb4','collation_connection':'utf8mb4_bin'}}}


def test_exact_library_creation_and_comment_only_alteration():
    before=row();after=row("'owner''s comment'")
    assert compile_library(before,'create','d`é').startswith('CREATE LIBRARY `d``é`.`l``é`')
    assert compile_library(after,'alter','d`é',before)=="ALTER LIBRARY `d``é`.`l``é` COMMENT 'owner''s comment'"
    empty=row();empty['native']['definition']=empty['native']['definition'].replace(" COMMENT 'initial'\n",'')
    assert compile_library(empty,'alter','d`é',before).endswith("COMMENT ''")
    dropped=deepcopy(before);dropped['native']['mysql_change']={'action':'drop','confirmation':'l`é'}
    assert compile_library(dropped,'drop','d`é',before)=='DROP LIBRARY `d``é`.`l``é`'


@pytest.mark.parametrize('after',[row(body="X'00ff'"),row(mode='NO_BACKSLASH_ESCAPES')])
def test_body_or_context_replacement_is_refused(after):
    with pytest.raises(ValueError,match='only COMMENT'):compile_library(after,'alter','db',row())


def test_wrong_targets_and_unconfirmed_removal_are_refused():
    changed=row();changed['name']='other'
    with pytest.raises(ValueError,match='identity'):compile_library(changed,'create','db')
    with pytest.raises(ValueError,match='confirmation'):compile_library(row(),'drop','db')
    changed=row("'x'; DROP DATABASE db; --")
    with pytest.raises(ValueError):compile_library(changed,'alter','db',row())


@pytest.mark.parametrize('mode,comment', [('',"'back\\\\slash\\\'quote'"),('NO_BACKSLASH_ESCAPES',"'back\\slash''quote'")])
def test_comment_quoting_uses_native_sql_mode(mode,comment):
    before=row(mode=mode);after=row(comment,mode=mode)
    assert compile_library(after,'alter','db',before).endswith('COMMENT '+comment)
