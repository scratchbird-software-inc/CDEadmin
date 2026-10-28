// Qualification/source maintenance only; all edits use DDN's public source API.
import {decodeSources,patchProperty,applySourcePatches} from '../web/pgadmin/static/vendor/ddn/current/modules/language/src/index.js';
import {admitWorkspace,sourceSet} from '../web/pgadmin/cdeadmin/workspace/ddn/workspace_admission.mjs';
let text='';for await(const chunk of process.stdin){text+=chunk;if(Buffer.byteLength(text)>16*1024*1024)throw Error('Source edit input limit exceeded');}
const {snapshot,edits}=JSON.parse(text);await admitWorkspace(snapshot);
if(!Array.isArray(edits) || edits.length>128)throw Error('Invalid source edits');
let input=sourceSet(snapshot);
for(const edit of edits) {
  const parsed=decodeSources({...input,entry:edit.target.file});
  if(!parsed.syntaxValid)throw Error('Invalid source before edit');
  input=applySourcePatches(input,patchProperty(parsed,edit.target,edit.path,edit.value));
}
const result={...snapshot,files:Object.fromEntries(input.files.map(file=>[file.id,file.text]))};
await admitWorkspace(result);process.stdout.write(JSON.stringify(result));
