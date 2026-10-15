// Feed captured native observations through the shipping adapters and DDN API.
import runtime from '../../web/pgadmin/static/vendor/ddn/current/ddn.mjs';
import {firebirdDashboardFiles, firebirdFleetFiles} from '../../web/pgadmin/static/js/cdeadmin_ui/integrations/ddn/firebirdDashboard.js';
import {validatePublication, bindPublication} from '../../web/pgadmin/static/js/cdeadmin_ui/integrations/ddn/dashboardPublication.mjs';
let input='';
for await(const chunk of process.stdin) input+=chunk;
const captures=JSON.parse(input), result={};
runtime.setTextProvider((text,size)=>({width:String(text).length*size*.6,ascent:size*.8,descent:size*.2}),'native-firebird-dashboard');
for(const scope of ['engine','server','database']) {
  const files=scope==='engine' ? firebirdFleetFiles(captures[scope]) : firebirdDashboardFiles(captures[scope],'Native Firebird dashboard',scope);
  const snapshot={format:'ddn-workspace@1',entry:'dashboard.ddn',view:'dashboard',files};
  const clean=validatePublication(runtime,snapshot,scope);
  const rows=source=>runtime.parse(source['dashboard.ddn']).declarations.find(node=>node.type==='data').children;
  if(rows(clean.files).some(row=>row.props.x_record.value!=='Unavailable')) throw new Error('Publication retained telemetry');
  const live=bindPublication(runtime,clean,scope,files);
  const expected=rows(files).map(row=>[row.id,row.props.x_record]);
  if(JSON.stringify(rows(live.files).map(row=>[row.id,row.props.x_record]))!==JSON.stringify(expected)) throw new Error('Native binding changed values or identities');
  const workspace=runtime.createWorkspace(live.files);
  let views=0;
  try {
    for(const entry of workspace.entries()) for(const view of entry.views) {
      const rendered=workspace.renderSync({entry:entry.file,view:view.id});
      if(!rendered.svg.includes('<svg') || rendered.diagnostics.some(item=>['error','incomplete'].includes(item.severity))) throw new Error('Invalid native dashboard view');
      views++;
    }
  } finally {workspace.destroy();}
  result[scope]={views,bindings:expected.length,redacted_publication:true,exact_native_rebinding:true};
}
process.stdout.write(JSON.stringify(result,null,2));
