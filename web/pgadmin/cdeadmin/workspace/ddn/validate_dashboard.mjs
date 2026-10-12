import runtime from '../../../static/vendor/ddn/current/ddn.mjs';
import {validatePublication} from '../../../static/js/cdeadmin_ui/integrations/ddn/dashboardPublication.mjs';
let input = '';
for await (const part of process.stdin) {
  input += part;
  if(input.length > 2 * 1024 * 1024) throw new Error('Input limit exceeded');
}
try {
  const {snapshot, scope, engine} = JSON.parse(input);
  process.stdout.write(JSON.stringify(validatePublication(runtime, snapshot, scope, engine)));
} catch {
  process.stderr.write('Dashboard source or metric bindings are invalid.');
  process.exitCode = 1;
}
