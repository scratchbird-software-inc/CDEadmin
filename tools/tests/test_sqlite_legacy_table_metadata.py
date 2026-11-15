"""Native older-runtime table flags and constructor-observed module storage."""
from contextlib import closing
import sqlite3
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.provider import _resources


@pytest.mark.parametrize('module,columns',[('fts3','body'),('fts4','body'),('fts5','body'),('rtree','id,min_x,max_x')])
def test_native_legacy_metadata_identifies_real_storage_without_hiding_lookalikes(module,columns):
    with closing(sqlite3.connect(':memory:')) as c:
        c.executescript('CREATE TABLE normal(id PRIMARY KEY);CREATE TABLE keyed(id PRIMARY KEY) WITHOUT ROWID;'
            'CREATE TABLE other_data(value);CREATE TABLE own_shadowlookalike(value);')
        c.execute('CREATE VIRTUAL TABLE own USING '+module+'('+columns+')')
        rows=_resources(c,{})
        relations={r['display_name']:r for r in rows if len(r['display_path'])==2}
        assert relations['normal']['native']['catalog_metadata']['table_list_type']=='table'
        assert relations['normal']['native']['catalog_metadata']['without_rowid'] is False
        assert relations['keyed']['native']['catalog_metadata']['without_rowid'] is True
        assert relations['own_shadowlookalike']['native']['system_object'] is False
        # FTS5 legitimately uses own_data: use an unrelated same-suffix table
        # for that module, and avoid conflicting with a real constructor name.
        assert c.execute('SELECT count(*) FROM normal').fetchone()==(0,)
        storage=[r for r in rows if r['native'].get('catalog_metadata',{}).get('table_list_type')=='shadow']
        assert storage and all(r['native']['system_object'] for r in storage)
