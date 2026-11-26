import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, mkdir, readFile, rm, stat, writeFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {
  connectionArguments, credentialEnvironment, terminalArguments,
  verifyIsql, prepareEmbeddedEnvironment, setupFirebirdIsql,
} from '../src/js/firebirdIsql.js';

const connection = {
  schema: 'scratchrobin.firebird.isql-context@1',
  database_target_id: 'owned',
  dsn: 'inet://[::1]:3051//srv/quoted name.fdb',
  user: 'Mixed User',
  role: 'Role',
  charset: 'UTF8',
  sql_dialect: 3,
};

test('native arguments preserve endpoint and identifiers without a shell', () => {
  const args = connectionArguments(connection);
  assert.deepEqual(args, ['-user', 'Mixed User', '-charset', 'UTF8', '-sql_dialect', '3', '-role', 'Role', connection.dsn]);
  assert.deepEqual(terminalArguments('/usr/bin/konsole', '/tools/isql', args), ['--separate', '--nofork', '-e', '/tools/isql', ...args]);
  assert.throws(() => terminalArguments('/bin/sh', '/tools/isql', args));
});

test('credentials replace inherited native identity only in the child environment', () => {
  const parent = {PATH: '/bin', ISC_USER: 'wrong', ISC_PASSWORD: 'old', ISC_DATABASE: 'wrong', ISC_ROLE: 'wrong'};
  const result = credentialEnvironment(parent, 'one-launch-secret');
  assert.deepEqual(result, {PATH: '/bin', ISC_PASSWORD: 'one-launch-secret'});
  assert.equal(parent.ISC_PASSWORD, 'old');
  assert.ok(!JSON.stringify(connectionArguments(connection)).includes('one-launch-secret'));
});

test('local paths on network contexts, invalid dialects, malformed values and extra command fields are rejected', () => {
  for (const bad of [{dsn: '/server/local.fdb'}, {sql_dialect: 2}, {user: 'a\nb'}, {extra: '-input evil.sql'}, {password: 'unexpected'}]) {
    assert.throws(() => connectionArguments({...connection, ...bad}));
  }
});

test('embedded same-host context validates containment, boot_id, inode and Engine13 provider', async () => {
  const tmp = await mkdtemp(path.join(os.tmpdir(), 'fb-isql-test-'));
  try {
    const dataDir = path.join(tmp, 'data');
    const rtDir = path.join(tmp, 'fb5');
    await mkdir(dataDir);
    await mkdir(path.join(rtDir, 'bin'), {recursive: true});
    await mkdir(path.join(rtDir, 'lib'), {recursive: true});
    await mkdir(path.join(rtDir, 'plugins'), {recursive: true});
    const fakeIsql = path.join(rtDir, 'bin', 'isql');
    await writeFile(fakeIsql, '');
    await writeFile(path.join(rtDir, 'plugins', 'libEngine13.so'), 'engine13');
    await writeFile(path.join(rtDir, 'plugins.conf'), '');
    const dbPath = path.join(dataDir, 'owned 雪.fdb');
    await writeFile(dbPath, 'db-bytes');
    const st = await stat(dbPath);
    const bootId = (await readFile('/proc/sys/kernel/random/boot_id', 'utf8')).trim();
    const embeddedConn = {
      schema: 'scratchrobin.firebird.isql-context@1',
      attachment_mode: 'embedded',
      database_target_id: 'owned-emb',
      database: dbPath,
      filesystem_root: dataDir,
      same_host_authority: {
        platform: 'linux',
        boot_id: bootId,
        hostname: os.hostname(),
        database_identity: {device: String(st.dev), inode: String(st.ino)},
        firebird_lock_directory: '',
      },
      native_provider: 'Engine13',
      password_required: false,
      user: 'SYSDBA',
      role: '',
      charset: 'UTF8',
      sql_dialect: 3,
    };
    assert.deepEqual(connectionArguments(embeddedConn), ['-user', 'SYSDBA', '-charset', 'UTF8', '-sql_dialect', '3', dbPath]);

    // Escape outside filesystem_root or network dsn mixing is rejected.
    assert.throws(() => connectionArguments({...embeddedConn, database: '/etc/passwd'}));
    assert.throws(() => connectionArguments({...embeddedConn, dsn: 'inet://127.0.0.1/db'}));

    // Different host boot_id is rejected before staging.
    await assert.rejects(
      prepareEmbeddedEnvironment(embeddedConn, fakeIsql, {PATH: '/bin'}, {bootId: '00000000-0000-0000-0000-000000000000', stageParent: tmp}),
      /same host/,
    );

    // Same host succeeds and stages Engine13-only firebird.conf without ISC_PASSWORD.
    const prepared = await prepareEmbeddedEnvironment(
      embeddedConn, fakeIsql,
      {PATH: '/bin', ISC_PASSWORD: 'stale'},
      {stageParent: tmp},
    );
    assert.equal(prepared.env.ISC_PASSWORD, undefined);
    const fbConf = await readFile(path.join(prepared.stagedConfigDir, 'firebird.conf'), 'utf8');
    assert.match(fbConf, /^Providers = Engine13$/m);

    // Replaced database inode is rejected.
    await rm(dbPath);
    const replacement = path.join(dataDir, 'other.fdb');
    await writeFile(replacement, 'other');
    const badSt = await stat(replacement);
    if (String(badSt.ino) !== String(st.ino)) {
      await writeFile(dbPath, 'recreated');
      const newSt = await stat(dbPath);
      if (String(newSt.ino) !== String(st.ino)) {
        await assert.rejects(
          prepareEmbeddedEnvironment(embeddedConn, fakeIsql, {PATH: '/bin'}, {stageParent: tmp}),
          /changed since the server issued/,
        );
      }
    }
  } finally {
    await rm(tmp, {recursive: true, force: true});
  }
});

test('a non-Firebird executable fails version admission', async () => {
  await assert.rejects(verifyIsql('/usr/bin/true'), /Firebird 5/);
});

test('desktop IPC admits same-origin top frame for both TCP and embedded launches', async () => {
  let handler, calls = 0, received;
  const frame = {url: 'http://127.0.0.1:5050/browser/'};
  const event = {sender: {mainFrame: frame}, senderFrame: frame};
  const dialog = {showOpenDialog: async () => ({canceled: false, filePaths: [++calls % 2 === 1 ? '/owned/isql' : '/usr/bin/konsole']})};
  setupFirebirdIsql({
    ipcMain: {handle: (_name, callback) => { handler = callback; }},
    BrowserWindow: {fromWebContents: () => ({isDestroyed: () => false})},
    dialog,
    getOrigin: () => 'http://127.0.0.1:5050',
    launch: async request => { received = request; return {state: 'process_started'}; },
  });
  await assert.rejects(handler({...event, senderFrame: {url: frame.url}}, {connection, password: 'only-this-launch'}));
  frame.url = 'http://127.0.0.1:5050.evil.invalid/';
  await assert.rejects(handler(event, {connection, password: 'only-this-launch'}));
  frame.url = 'http://127.0.0.1:5050/browser/';
  assert.deepEqual(await handler(event, {connection, password: 'only-this-launch'}), {state: 'process_started'});
  assert.deepEqual(received, {connection, password: 'only-this-launch', executable: '/owned/isql', terminal: '/usr/bin/konsole'});

  const embConn = {
    schema: 'scratchrobin.firebird.isql-context@1',
    attachment_mode: 'embedded',
    database_target_id: 'owned-emb',
    database: '/srv/root/db.fdb',
    filesystem_root: '/srv/root',
    same_host_authority: {
      platform: 'linux', boot_id: 'boot-1', hostname: 'host-1',
      database_identity: {device: '1', inode: '2'}, firebird_lock_directory: '',
    },
    native_provider: 'Engine13',
    password_required: false,
    user: 'SYSDBA', role: '', charset: 'UTF8', sql_dialect: 3,
  };
  await assert.rejects(handler(event, {connection: embConn, password: 'secret-not-allowed'}), /does not accept a network password/);
  assert.deepEqual(await handler(event, {connection: embConn}), {state: 'process_started'});
  assert.equal(received.connection.attachment_mode, 'embedded');

  received = null;
  dialog.showOpenDialog = async () => ({canceled: true});
  assert.deepEqual(await handler(event, {connection, password: 'only-this-launch'}), {state: 'cancelled_before_launch'});
  assert.equal(received, null);
  dialog.showOpenDialog = async () => { frame.url = 'https://other.invalid/'; return {canceled: false, filePaths: ['/owned/isql']}; };
  await assert.rejects(handler(event, {connection, password: 'only-this-launch'}));
  assert.equal(received, null);
});
