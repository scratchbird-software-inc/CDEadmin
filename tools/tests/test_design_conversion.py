"""Exercise source-preserving refresh through the adopted public DDN APIs."""
from copy import deepcopy
import subprocess
import pytest
from pgadmin.cdeadmin.workspace import ddn_source as ddn
from pgadmin.cdeadmin.workspace.design_conversion import merge_design


def snapshot(name='Old', module='test.engine.one'):
    return ddn.workspace({'design.ddn': ddn.header(module) + ddn.record_definition('a',name,{'value':name},module=module,block='items') + ddn.table_view('v','Native',['items.a'],[{'key':'name','label':'Name'}])},'design.ddn','v')


@pytest.mark.parametrize('module',['test.engine.one','test.engine.two'])
def test_refresh_is_engine_independent_and_retains_authored_appearance(module):
    original=snapshot(module=module);authored=deepcopy(original)
    authored['files']['design.ddn']=authored['files']['design.ddn'].replace('title "Native"','// retained annotation 🦉\n        title "Authored"')
    request={'baseline':original,'draft':authored,'incoming':snapshot('New',module)};before=deepcopy(request)
    result=merge_design(request)
    assert 'value "New"' in result['files']['design.ddn']
    assert '// retained annotation 🦉\n        title "Authored"' in result['files']['design.ddn']
    assert request==before


def test_native_conflicts_do_not_discard_authored_edits():
    request={'baseline':snapshot(),'draft':snapshot('Authored'),'incoming':snapshot('New')};before=deepcopy(request)
    with pytest.raises(ValueError,match='changed on both sides'):merge_design(request)
    assert request==before
    assert merge_design({**request,'incoming':snapshot()})==request['draft']


def test_validation_checks_preserved_views_against_new_native_blocks():
    incoming=snapshot('New')
    incoming['files']['design.ddn']=incoming['files']['design.ddn'].replace('items.a','items.b')
    with pytest.raises(ValueError):merge_design({'baseline':snapshot(),'draft':snapshot(),'incoming':incoming})


@pytest.mark.parametrize('path',['../a.ddn','/a.ddn','a.ddna','a.ddnn','a\\b.ddn'])
def test_source_boundary_rejects_unsupported_formats_and_paths(path):
    value=snapshot();value['files']={path:value['files']['design.ddn']};value['entry']=path
    with pytest.raises(ValueError,match='Invalid DDN source file'):merge_design({'baseline':value,'draft':value,'incoming':value})


def test_timeout_releases_capacity_and_retains_draft(monkeypatch):
    request={'baseline':snapshot(),'draft':snapshot(),'incoming':snapshot()};before=deepcopy(request)
    with monkeypatch.context() as patch:
        def timeout(*args,**kwargs):raise subprocess.TimeoutExpired('node',30)
        patch.setattr(subprocess,'run',timeout)
        with pytest.raises(ValueError,match='unavailable'):merge_design(request)
    assert request==before
    assert merge_design(request)==request['draft']


def test_authored_only_files_are_parsed_and_selected_view_must_exist():
    authored=snapshot();authored['files']['extra.ddn']='invalid document'
    with pytest.raises(ValueError):merge_design({'baseline':snapshot(),'draft':authored,'incoming':snapshot()})
    authored['files']['extra.ddn']='version ddn-next-1\ninclude "design.ddn"\n'
    assert merge_design({'baseline':snapshot(),'draft':authored,'incoming':snapshot()})==authored
    authored=snapshot();authored['view']='missing'
    with pytest.raises(ValueError,match='selected.*view'):merge_design({'baseline':snapshot(),'draft':authored,'incoming':snapshot()})


def imported(name='Old'):
    value=snapshot(name);source=value['files'].pop('design.ddn');model,view=source.split('view "v"',1)
    value['entry']='views/main.ddn';value['files']={'model.ddn':model,'views/main.ddn':ddn.header('test.engine.views')+'include "../model.ddn"\n'+ddn.table_view('v','Native',[ddn.ref('items.a','../model.ddn')],[{'key':'name','label':'Name'}])}
    return value


def test_imported_refresh_preserves_authored_view_and_updates_native_block():
    baseline=imported();draft=deepcopy(baseline);draft['files']['views/main.ddn']=draft['files']['views/main.ddn'].replace('"Native"','"Authored"')
    result=merge_design({'baseline':baseline,'draft':draft,'incoming':imported('New')})
    assert 'value "New"' in result['files']['model.ddn']
    assert result['files']['views/main.ddn']==draft['files']['views/main.ddn']
    with pytest.raises(ValueError,match='changed on both sides'):merge_design({'baseline':baseline,'draft':imported('Authored'),'incoming':imported('New')})
