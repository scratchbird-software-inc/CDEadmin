import * as viewer from '../../../static/vendor/ddn/current/complete/ddn-verifier.js';
import * as language from '../../../static/vendor/ddn/current/modules/language/src/index.js';
import * as model from '../../../static/vendor/ddn/current/modules/model/src/index.js';
import {validatePublication} from '../../../static/js/cdeadmin_ui/integrations/ddn/dashboardPublication.mjs';
let input = '';
for await (const part of process.stdin) {
  input += part;
  if(input.length > 2 * 1024 * 1024) throw new Error('Input limit exceeded');
}
try {
  const {snapshot, scope, engine} = JSON.parse(input);
  process.stdout.write(JSON.stringify(await validatePublication({viewer,language,model}, snapshot, scope, engine)));
} catch {
  process.stderr.write('Dashboard source or metric bindings are invalid.');
  process.exitCode = 1;
}
