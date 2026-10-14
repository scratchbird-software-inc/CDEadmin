"""Real DDN reader/rendering of exact PostgreSQL buffered result values."""
import json
import subprocess
from pathlib import Path

import pytest
from pgadmin.cdeadmin.results.ddn_export import export_workspace
from pgadmin.cdeadmin.results.models import ResultLimitError


def metadata():
    return {'result_id':'result', 'execution_id':'execution', 'complete':False,
            'provider_continuation':'private-handle-not-for-export',
            'schema':{'columns':[{'name':'duplicate','key':'c0','type':'numeric'},
                                 {'name':'duplicate','key':'c1','type':'bytea'}]},
            'export_coverage':{'stored_records':2,'exported_records':2,'sampling_applied':False}}


def test_exact_positional_values_and_coverage_render_through_public_ddn():
    rows = [{'c0':'12345678901234567890.123456789','c1':{'type':'binary','value':'AP8='}},
            {'c0':None,'c1':'null'}]
    snapshot = json.loads(export_workspace(metadata(), rows))
    source = snapshot['files'][snapshot['entry']]
    assert 'private-handle-not-for-export' not in source
    runtime = (Path(__file__).resolve().parents[2]/'web/pgadmin/static/vendor/ddn/current/ddn.mjs').as_uri()
    script = f'''import runtime from {json.dumps(runtime)};
      let input='';for await(const chunk of process.stdin) input+=chunk;
      const snapshot=JSON.parse(input), workspace=runtime.createWorkspace(snapshot.files);
      try {{for(const entry of workspace.entries()) for(const view of entry.views) {{
        const result=workspace.renderSync({{entry:entry.file,view:view.id}});
        const errors=result.diagnostics.filter(x=>x.severity==='error');
        if(errors.length) throw new Error(JSON.stringify(errors));
        if(!result.svg.includes('12345678901234567890.123456789')) throw new Error('Lost decimal');
        if(!result.svg.includes('duplicate')) throw new Error('Lost labels');
      }}}} finally {{workspace.destroy();}}
      process.stdout.write('PASS');'''
    result = subprocess.run(['node','--input-type=module','-e',script],input=json.dumps(snapshot),
                            text=True,capture_output=True,timeout=15)
    assert result.returncode == 0, result.stderr
    assert 'selection_complete' not in source  # Caller owns coverage, renderer invents none.
    assert 'provider_continuation_remaining' in source
    assert 'values_json' in source and 'c_0' in source and 'c_1' in source


def test_bounded_views_preserve_all_selected_rows_and_empty_results():
    result = json.loads(export_workspace(metadata(), [[str(i),None] for i in range(401)]))
    assert len(result['files']) == 5
    assert sum(text.count('record r_') for text in result['files'].values()) == 401
    empty = json.loads(export_workspace(metadata(), []))
    assert 'No rows in this export' in empty['files'][empty['entry']]


def test_refuses_shape_or_size_loss_instead_of_silent_truncation():
    with pytest.raises(ResultLimitError,match='column metadata'):
        export_workspace(metadata(), [[1]])
    with pytest.raises(ResultLimitError,match='document limit'):
        export_workspace(metadata(), [['x'*2000000,None]])


def test_result_service_applies_owner_scope_redaction_and_selection_coverage():
    from tools.tests.test_cdeadmin_result_renderers import harness, result, CAPABILITY
    from pgadmin.cdeadmin.results.models import ResultDescriptorError
    ctx, provider, registry, service = harness()
    provider.normalized['export_policy']['formats'].append('ddn')
    provider.normalized['export_policy']['max_records'] = 1
    admitted = service.admit_provider_result(ctx, result(), {CAPABILITY})
    output = service.export(admitted['result_id'], 'ddn', endpoint_id=ctx.endpoint_id)
    assert b'do-not-render' not in output['content']
    assert output['records'] == 1
    assert b'stored_records' in output['content'] and b'selection_complete' in output['content']
    with pytest.raises(ResultDescriptorError):
        service.export(admitted['result_id'], 'ddn', endpoint_id='different-owner-endpoint')


def test_multi_page_export_fits_paired_runtime_live_view_element_limits():
    snapshot=json.loads(export_workspace(metadata(), [[str(i),None] for i in range(257)]))
    runtime=(Path(__file__).resolve().parents[2]/'web/pgadmin/static/vendor/ddn/current/ddn.mjs').as_uri()
    script='import runtime from '+json.dumps(runtime)+";let input='';for await(const part of process.stdin)input+=part;const s=JSON.parse(input),w=runtime.createWorkspace(s.files);try{for(const entry of w.entries())for(const view of entry.views){const result=w.renderSync({entry:entry.file,view:view.id});if(result.diagnostics.some(x=>x.severity==='error'))throw Error('Invalid multi-page DDN');}}finally{w.destroy();}"
    result=subprocess.run(['node','--input-type=module','-e',script],input=json.dumps(snapshot),text=True,capture_output=True,timeout=30)
    assert result.returncode==0,result.stderr
