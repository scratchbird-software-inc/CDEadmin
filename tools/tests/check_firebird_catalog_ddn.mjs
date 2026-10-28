// Real source/model/semantic admission. Browser capture is qualified separately.
import {admitWorkspace,mapping} from '../../web/pgadmin/cdeadmin/workspace/ddn/workspace_admission.mjs';
let input='';for await(const chunk of process.stdin) input+=chunk;
const value=JSON.parse(input), result=value.snapshot?value:{snapshot:value};
const documents=await admitWorkspace(result.snapshot), recovered={};
for(const doc of documents.values()) for(const row of doc.records) {
  const fields=mapping(row.record)?.record;
  if(fields?.resource_id) recovered[fields.resource_id]=fields.native_json;
}
if(result.diagram?.snapshot) await admitWorkspace(result.diagram.snapshot);
process.stdout.write(JSON.stringify(recovered));
