// Captured observations pass the shipping adapters, semantic verifier and SDK.
import * as viewer from '../../web/pgadmin/static/vendor/ddn/current/complete/ddn-verifier.js';
import * as language from '../../web/pgadmin/static/vendor/ddn/current/modules/language/src/index.js';
import * as model from '../../web/pgadmin/static/vendor/ddn/current/modules/model/src/index.js';
import {renderWorkspace} from '../ddn_render.mjs';
import {sourceSet} from '../../web/pgadmin/cdeadmin/workspace/ddn/workspace_admission.mjs';
import {firebirdDashboardFiles,firebirdFleetFiles} from '../../web/pgadmin/static/js/cdeadmin_ui/integrations/ddn/firebirdDashboard.js';
import {validatePublication,bindPublication} from '../../web/pgadmin/static/js/cdeadmin_ui/integrations/ddn/dashboardPublication.mjs';
let input='';for await(const chunk of process.stdin)input+=chunk;
const captures=JSON.parse(input),result={},libraries={viewer,language,model};
const rows=snapshot=>model.listRecords(language.decodeSources(sourceSet(snapshot)).normalized).find(row=>row.kind==='data' && row.ref.id==='observations').record.rows;
for(const scope of ['engine','server','database']) {
  const files=scope==='engine'?firebirdFleetFiles(captures[scope]):firebirdDashboardFiles(captures[scope],'Native dashboard',scope);
  const snapshot={format:'ddn-source-workspace@1',entry:'dashboard.ddn',view:'dashboard',files};
  const clean=await validatePublication(libraries,snapshot,scope);
  if(rows(clean).some(row=>row[3]!=='Unavailable'))throw Error('Publication retained telemetry');
  const bound=await bindPublication(libraries,clean,scope,files);
  if(JSON.stringify(bound.liveData[0].rows)!==JSON.stringify(rows(snapshot)))throw Error('Native binding changed values or identities');
  const rendered=await renderWorkspace(snapshot);
  result[scope]={views:rendered.views.length,bindings:rows(snapshot).length,redacted_publication:true,exact_native_rebinding:true};
}
process.stdout.write(JSON.stringify(result,null,2));
