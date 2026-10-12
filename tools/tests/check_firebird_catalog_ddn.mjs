// Public DDN parser/render contract check for exported catalog source.
import runtime from '../../web/pgadmin/static/vendor/ddn/current/ddn.mjs';
process.stdin.setEncoding('utf8');
let input = '';
for await (const chunk of process.stdin) input += chunk;
const result = JSON.parse(input);
const workspace = runtime.createWorkspace(result.snapshot.files);
try {
  const recovered = {};
  for(const [name, source] of Object.entries(result.snapshot.files)) {
  const parsed = runtime.parse(source, name);
  for(const block of parsed.declarations.filter((item) => item.type === 'data')) {
    for(const row of block.children) {
      const fields = row.props.x_record;
      if(fields?.resource_id) recovered[fields.resource_id] = fields.native_json;
    }
  }
  }
  for(const view of result.views) {
    const rendered = workspace.renderSync({entry: view.entry || result.snapshot.entry, view: view.id});
    if(rendered.diagnostics.some((item) => item.severity === 'error')) {
      throw new Error('Invalid catalog view');
    }
  }
  if(result.diagram?.snapshot) {
    const diagram = runtime.createWorkspace(result.diagram.snapshot.files);
    try {for(const view of result.diagram.views) {
      const rendered = diagram.renderSync({entry:view.entry, view:view.id});
      const errors = rendered.diagnostics.filter(item => item.severity === 'error');
      if(errors.length) throw new Error(JSON.stringify(errors));
    }} finally {diagram.destroy();}
  }
  process.stdout.write(JSON.stringify(recovered));
} finally {workspace.destroy();}
