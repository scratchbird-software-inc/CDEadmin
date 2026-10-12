/* Real-browser qualification of the vendored DDN public tool bridge.
 * Run tools/refresh_ddn.py first. All browser state is confined to TMPDIR. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const cp = require('node:child_process');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const vendor = path.join(root, 'web/pgadmin/static/vendor/ddn/current');
const cache = process.env.PLAYWRIGHT_BROWSERS_PATH || path.join(os.homedir(), '.cache/ms-playwright');
const shells = fs.existsSync(cache) ? fs.readdirSync(cache).filter(n => n.startsWith('chromium_headless_shell-')).sort() : [];
const browser = process.env.DDN_BROWSER || path.join(cache, shells.at(-1) || '', 'chrome-headless-shell-linux64/chrome-headless-shell');
if (!fs.existsSync(browser)) throw Error('Set DDN_BROWSER to a Chromium executable.');
if (!process.env.TMPDIR) throw Error('Set TMPDIR to the designated artifact directory.');
const profile = fs.mkdtempSync(path.join(process.env.TMPDIR, 'ddn-browser-'));
let child, timer;
const hangs = [];
const source = 'ddn "0.5"; module "test"; data model { object a "Alpha" { kind: table; } } view main { data: [@model]; select: [@model.a]; }';
const page = `<!doctype html><iframe id="editor" src="/ddn-tool.html?mode=design&worker=off" style="width:1200px;height:850px"></iframe><img src="/hang" hidden><script>
const frame = document.getElementById('editor');
frame.onload = async () => {
 try {
  const tool = frame.contentWindow.DDNTool;
  if (!tool) throw Error('missing DDNTool');
  const loaded = await tool.setSource({'model.ddn': ${JSON.stringify(source)}});
  const before = tool.getSource({includeAppearance:true});
  let notifications = 0;
  const off = tool.onSourceChange(() => notifications++);
  tool.workspace.updateFiles({'model.ddn': before.files['model.ddn'].replace('Alpha','Beta')});
  await new Promise(resolve => setTimeout(resolve, 600));
  const edited = tool.getSource({includeAppearance:true});
  if (!edited.files['model.ddn'].includes('Beta')) throw Error('source edit lost');
  if (!notifications) throw Error('source change notification missing');
  off();
  await tool.setSource(edited.files, {entry:edited.entry, view:edited.view});
  const after = tool.getSource({includeAppearance:true});
  if (JSON.stringify(edited.files) !== JSON.stringify(after.files)) throw Error('round trip changed source');
  if (!tool.exportSvgString().includes('<svg')) throw Error('SVG missing');
  await fetch('/result',{method:'POST', body: JSON.stringify({pass:true, loaded, notifications, files:Object.keys(after.files)})});
 } catch (error) { await fetch('/result',{method:'POST',body:JSON.stringify({pass:false,error:error.message,stack:error.stack})}); }
};
</script>`;
const server = http.createServer((req, res) => {
 const pathname = new URL(req.url, 'http://localhost').pathname;
 if (pathname === '/hang') { hangs.push(res); return; }
 if (pathname === '/result' && req.method === 'POST') {
  let body = ''; req.on('data', chunk => { body += chunk; });
  req.on('end', () => {
   res.end('ok');
   try { const result = JSON.parse(body); console.log(JSON.stringify(result)); assert.equal(result.pass, true); }
   catch (error) { console.error(error.message); process.exitCode = 1; }
   finish();
  }); return;
 }
 if (pathname === '/') { res.setHeader('content-type','text/html'); res.end(page); return; }
 if (pathname === '/ddn-tool.html') { res.setHeader('content-type','text/html'); fs.createReadStream(path.join(vendor,'ddn-tool.html')).pipe(res); return; }
 res.writeHead(404); res.end();
});
function finish() {
 clearTimeout(timer);
 for (const res of hangs) res.end();
 if (child) child.kill();
 server.close();
}
server.listen(0, '127.0.0.1', () => {
 child = cp.spawn(browser, ['--headless','--no-sandbox','--disable-gpu', '--no-first-run',
  '--user-data-dir=' + profile, '--dump-dom', 'http://127.0.0.1:' + server.address().port], {stdio:['ignore','ignore','pipe']});
 child.stderr.on('data', data => process.stderr.write(data));
 child.on('exit', () => { fs.rmSync(profile, {recursive:true,force:true}); });
 child.on('error', error => { console.error(error.message); process.exitCode=1; finish(); });
 timer = setTimeout(() => { console.error('DDN bridge test timed out'); process.exitCode=1; finish(); }, 60000);
});
