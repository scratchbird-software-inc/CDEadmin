import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, readFile, readdir, rm, writeFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {FirebirdDocker, configuration, createArguments, setupFirebirdDocker} from '../src/js/firebirdDocker.js';

const config = {context: 'default', container: 'test-firebird', storage: 'volume', volume: 'test-firebird-data',
  bind: '127.0.0.1', port: 13050, eventPort: 13051, database: 'test.fdb', version: '5.0.4'};
const image = 'sha256:' + 'a'.repeat(64), container = 'b'.repeat(64);
test('context discovery returns only explicit routing facts and does not mutate Docker', async () => {
  const calls = [];
  const service = new FirebirdDocker({root: os.tmpdir(), execute: async (_binary, args) => {
    calls.push(args);
    return args[0] === '--version' ? 'Docker version 29.0.0' : JSON.stringify({Name: 'desktop-linux',
      DockerEndpoint: 'unix:///owned/docker.sock', Current: true, Description: 'not returned'});
  }});
  const result = await service.contexts('/usr/bin/true');
  assert.deepEqual(result.contexts, [{name: 'desktop-linux', endpoint: 'unix:///owned/docker.sock', current: true}]);
  assert.deepEqual(calls[1], ['context', 'ls', '--format', '{{json .}}']);
});
function daemon() {
  const calls = []; let owner, identity = 'daemon-A';
  return {calls, identity: value => {identity = value;}, execute: async (binary, args, env) => {
    calls.push({args, env});
    assert.equal(env.DOCKER_HOST, undefined); assert.equal(env.FIREBIRD_CONF_Danger, undefined);
    if (args[0] === '--version') return 'Docker version 29.0.0';
    if (args.includes('context') && args.includes('inspect')) return JSON.stringify('unix:///var/run/docker.sock');
    if (args.includes('info')) return JSON.stringify(identity);
    if (args.includes('image')) return JSON.stringify(image);
    if (args.includes('ls')) return '';
    if (args.includes('volume') && args.includes('create')) {owner = args[args.indexOf('--label') + 1].split('=')[1]; return config.volume;}
    if (args.includes('volume') && args.includes('inspect')) return owner;
    if (args.includes('create')) return container;
    if (args.includes('start')) return container;
    if (args.includes('inspect')) return 'true';
    throw new Error('Unexpected command');
  }};
}
test('configuration and native arguments have exact image, ports and storage without a password argument', () => {
  for (const bad of [{version: 'latest'}, {container: 'a; echo injected'}, {eventPort: 3050}, {port: 0}, {database: '../other.fdb'}, {extra: true}]) assert.throws(() => configuration({...config, ...bad}));
  const args = createArguments({configuration: config, review_id: 'review', image_id: image});
  assert.ok(args.includes('127.0.0.1:13051:13051'));
  assert.ok(args.includes('FIREBIRD_CONF_RemoteAuxPort=13051'));
  assert.ok(args.includes('type=volume,source=test-firebird-data,target=/var/lib/firebird/data'));
  assert.equal(args.at(-1), image);
  assert.ok(args.includes('--pull=never'));
  assert.ok(args.includes('FIREBIRD_ROOT_PASSWORD'));
  assert.ok(!args.some(value => value.startsWith('FIREBIRD_ROOT_PASSWORD=')));
});
test('preparation is noncreating, apply is consumed once, receipts survive restart and contain no credentials', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'firebird-docker-test-'));
  try {
    const fake = daemon(), service = new FirebirdDocker({root, execute: fake.execute, env: {DOCKER_HOST: 'wrong', FIREBIRD_CONF_Danger: 'wrong'}});
    const review = await service.prepare({executable: '/usr/bin/true', config, owner: 1});
    assert.ok(!fake.calls.some(call => call.args.includes('create') || call.args.includes('start')));
    await assert.rejects(service.apply({review_id: review.review_id, password: 'only-bootstrap', confirmed: true, owner: 2}));
    const result = await service.apply({review_id: review.review_id, password: 'only-bootstrap', confirmed: true, owner: 1});
    assert.equal(result.state, 'container_running'); assert.equal(result.native_connection_verified, false);
    const create = fake.calls.find(call => call.args.includes('create') && !call.args.includes('volume'));
    assert.equal(create.env.FIREBIRD_ROOT_PASSWORD, 'only-bootstrap');
    assert.ok(!JSON.stringify(create.args).includes('only-bootstrap'));
    await assert.rejects(service.apply({review_id: review.review_id, password: 'only-bootstrap', confirmed: true, owner: 1}));
    const restarted = new FirebirdDocker({root, execute: fake.execute});
    assert.deepEqual(await restarted.receipt(review.review_id), result);
    await assert.rejects(restarted.apply({review_id: review.review_id, password: 'x', confirmed: true, owner: 1}));
    const files = await readdir(root); assert.deepEqual(files, [review.review_id + '.json']);
    assert.ok(!(await readFile(path.join(root, files[0]), 'utf8')).includes('only-bootstrap'));
  } finally {await rm(root, {recursive: true, force: true});}
});
test('changed daemon and changed local directory stop before storage or container creation', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'firebird-docker-change-'));
  try {
    const fake = daemon(), service = new FirebirdDocker({root, execute: fake.execute});
    const review = await service.prepare({executable: '/usr/bin/true', config, owner: 1});
    fake.identity('daemon-B');
    const result = await service.apply({review_id: review.review_id, password: 'x', confirmed: true, owner: 1});
    assert.equal(result.state, 'unconfirmed_or_partial');
    assert.ok(!fake.calls.some(call => call.args.includes('create')));
    const dir = await mkdtemp(path.join(root, 'empty-'));
    const second = await service.prepare({executable: '/usr/bin/true', config: {...config, storage: 'directory'}, directory: dir, owner: 1});
    await writeFile(path.join(dir, 'new-file'), 'preserve');
    const changed = await service.apply({review_id: second.review_id, password: 'x', confirmed: true, owner: 1});
    assert.equal(changed.state, 'unconfirmed_or_partial');
    assert.equal(await readFile(path.join(dir, 'new-file'), 'utf8'), 'preserve');
    assert.ok(!fake.calls.some(call => call.args.includes('create')));
  } finally {await rm(root, {recursive: true, force: true});}
});
test('a lost container response retains the last phase and never removes storage or retries', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'firebird-docker-failure-'));
  try {
    const fake = daemon(), service = new FirebirdDocker({root, execute: async (...args) => {
      if (args[1].includes('create') && !args[1].includes('volume')) throw new Error('lost');
      return fake.execute(...args);
    }});
    const review = await service.prepare({executable: '/usr/bin/true', config, owner: 1});
    const result = await service.apply({review_id: review.review_id, password: 'x', confirmed: true, owner: 1});
    assert.equal(result.last_phase, 'creating_container'); assert.equal(result.volume_created, config.volume);
    assert.ok(!fake.calls.some(call => call.args.includes('rm') || call.args.includes('start')));
  } finally {await rm(root, {recursive: true, force: true});}
});
test('IPC requires its current top frame and rechecks native dialog navigation', async () => {
  const handlers = {}, frame = {url: 'http://127.0.0.1:5050/browser/'}, event = {sender: {mainFrame: frame, id: 3}, senderFrame: frame};
  let calls = 0;
  const dialog = {showOpenDialog: async () => {calls++; return {canceled: true};}};
  setupFirebirdDocker({ipcMain: {handle: (name, fn) => {handlers[name] = fn;}}, BrowserWindow: {fromWebContents: () => ({isDestroyed: () => false})},
    dialog, getOrigin: () => 'http://127.0.0.1:5050', service: {prepare: () => {throw new Error('must not call');}}});
  await assert.rejects(handlers['firebird-docker:prepare']({...event, senderFrame: {url: frame.url}}, config));
  assert.equal(calls, 0);
  assert.equal((await handlers['firebird-docker:prepare'](event, config)).state, 'cancelled_before_preparation');
  dialog.showOpenDialog = async () => {frame.url = 'https://other.invalid/'; return {canceled: false, filePaths: ['/usr/bin/docker']};};
  await assert.rejects(handlers['firebird-docker:prepare'](event, config));
});
