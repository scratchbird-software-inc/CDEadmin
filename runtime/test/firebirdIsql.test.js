import test from 'node:test';
import assert from 'node:assert/strict';
import {connectionArguments, credentialEnvironment, terminalArguments, verifyIsql, setupFirebirdIsql} from '../src/js/firebirdIsql.js';
const connection = {schema: 'scratchrobin.firebird.isql-context@1', database_target_id: 'owned',
  dsn: 'inet://[::1]:3051//srv/quoted name.fdb', user: 'Mixed User', role: 'Role', charset: 'UTF8', sql_dialect: 3};

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
test('local paths, invalid dialects, malformed values and extra command fields are rejected', () => {
  for (const bad of [{dsn: '/server/local.fdb'}, {sql_dialect: 2}, {user: 'a\nb'}, {extra: '-input evil.sql'}, {password: 'unexpected'}]) {
    assert.throws(() => connectionArguments({...connection, ...bad}));
  }
});
test('a non-Firebird executable fails version admission', async () => {
  await assert.rejects(verifyIsql('/usr/bin/true'), /Firebird 5/);
});


test('desktop IPC admits only its current same-origin top frame and native selections', async () => {
  let handler, calls=0, received;
  const frame={url: 'http://127.0.0.1:5050/browser/'};
  const event={sender: {mainFrame: frame}, senderFrame: frame};
  const dialog={showOpenDialog: async () => ({canceled: false, filePaths: [++calls === 1 ? '/owned/isql' : '/usr/bin/konsole']})};
  setupFirebirdIsql({ipcMain:{handle: (_name, callback) => {handler=callback;}},
    BrowserWindow:{fromWebContents: () => ({isDestroyed: () => false})}, dialog,
    getOrigin: () => 'http://127.0.0.1:5050', launch: async request => {received=request;return {state:'process_started'};}});
  await assert.rejects(handler({...event, senderFrame:{url: frame.url}}, {connection,password:'only-this-launch'}));
  frame.url='http://127.0.0.1:5050.evil.invalid/';
  await assert.rejects(handler(event, {connection,password:'only-this-launch'}));
  frame.url='http://127.0.0.1:5050/browser/';
  assert.equal(calls,0);
  assert.deepEqual(await handler(event,{connection,password:'only-this-launch'}),{state:'process_started'});
  assert.deepEqual(received,{connection,password:'only-this-launch',executable:'/owned/isql',terminal:'/usr/bin/konsole'});
  received=null;
  dialog.showOpenDialog=async () => ({canceled:true});
  assert.deepEqual(await handler(event,{connection,password:'only-this-launch'}),{state:'cancelled_before_launch'});
  assert.equal(received,null);
  dialog.showOpenDialog=async () => {frame.url='https://other.invalid/';return {canceled:false,filePaths:['/owned/isql']};};
  await assert.rejects(handler(event,{connection,password:'only-this-launch'}));
  assert.equal(received,null);
});
