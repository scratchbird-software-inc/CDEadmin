const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {test} = require('node:test');
const {collect} = require('./index.cjs');

test('preserves receipts and screenshots while excluding private keys and owned data', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'cdeadmin-evidence-test-'));
  try {
    for (const name of ['receipt.json', 'verify/python.xml', 'verify/workbench.png', 'fixtures/qualification.log',
      'fixtures/server.key', 'fixtures/owned-test/private.json', 'ddn-intake/snapshot/private.json',
      'mariadb-parent-test/build/source.json']) {
      const target = path.join(root, name);
      fs.mkdirSync(path.dirname(target), {recursive: true});
      fs.writeFileSync(target, 'fixture');
    }
    assert.deepEqual(collect(root).map(f => path.relative(root, f).split(path.sep).join('/')).sort(),
      ['fixtures/qualification.log', 'receipt.json', 'verify/python.xml', 'verify/workbench.png']);
  } finally {fs.rmSync(root, {recursive: true, force: true});}
});
