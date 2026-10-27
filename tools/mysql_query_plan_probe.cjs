// Exercise the production normalizer against plans returned by the native API.
const fs = require('fs');
const path = require('path');
const Module = require('module');
const root = path.resolve(__dirname, '..');
const filename = path.join(root, 'web/pgadmin/static/js/Dialogs/mysqlPlanPresentation.js');
const requireWeb = Module.createRequire(path.join(root, 'web/package.json'));
const babel = requireWeb('@babel/core');
const compiled = babel.transformFileSync(filename, {babelrc: false, configFile: false,
  presets: [[requireWeb.resolve('@babel/preset-env'), {targets: {node: 'current'}, modules: 'commonjs'}]]});
const loaded = new Module(filename, module);
loaded.paths = Module._nodeModulePaths(path.dirname(filename));
loaded._compile(compiled.code, filename);
const {mysqlPlanText, parseMySQLPlan} = loaded.exports;
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
const results = cases.map(item => {
  const text = mysqlPlanText(item.rendered);
  if (text !== item.native_text) throw new Error('Rendered native plan text changed: ' + item.name);
  const plan = parseMySQLPlan(text);
  if (!plan.available || plan.format !== item.format) throw new Error('Native format not graphed: ' + item.name + ' ' + plan.reason);
  if (item.min_nodes && plan.nodes.length < item.min_nodes) throw new Error('Native join edges missing: ' + item.name);
  if (item.actual && !plan.hasActual) throw new Error('Actual observations lost: ' + item.name);
  return {name: item.name, format: plan.format, node_count: plan.nodes.length,
    native_text_unchanged: true, actual_observations: plan.hasActual};
});
process.stdout.write(JSON.stringify({complete: true, cases: results}) + '\n');
