/** Native Linux qualification against explicitly owned desktop fixtures. */
import assert from 'node:assert/strict';
import {execFile} from 'node:child_process';
import {readFile, writeFile} from 'node:fs/promises';
import path from 'node:path';
import {FirebirdDocker} from '../runtime/src/js/firebirdDocker.js';
import {launchIsql} from '../runtime/src/js/firebirdIsql.js';

const [mode, input, output] = process.argv.slice(2);
const selected = JSON.parse(await readFile(input, 'utf8'));
const password = process.env.CDEADMIN_NATIVE_FIXTURE_PASSWORD;
assert.ok(password);
if (mode === 'docker') {
  const calls = [];
  const execute = async (executable, args, env, timeout=30000) => {
    calls.push(args);
    assert.ok(!JSON.stringify(args).includes(password));
    const result = await new Promise((resolve, reject) => execFile(executable, args,
      {env, timeout, maxBuffer: 2 * 1024 * 1024, shell: false}, (error, stdout) => {
        if (error) reject(new Error('Native Docker command failed.'));
        else resolve(stdout.trim());
      }));
    if (selected.lose_create_response && args.includes('create') && !args.includes('volume')) {
      throw new Error('Injected lost response after actual container creation.');
    }
    return result;
  };
  const root = path.join(path.dirname(output), 'receipts');
  const service = new FirebirdDocker({root, execute});
  const review = await service.prepare({executable: selected.executable, config: selected.configuration,
    directory: selected.directory, owner: 'owned-native-qualification'});
  assert.ok(!calls.some(args => args.includes('create') || args.includes('start')));
  const receipt = await service.apply({review_id: review.review_id, password, confirmed: true,
    owner: 'owned-native-qualification'});
  assert.equal(receipt.state, selected.lose_create_response ? 'unconfirmed_or_partial' : 'container_running');
  if (selected.lose_create_response) assert.equal(receipt.last_phase, 'creating_container');
  await assert.rejects(service.apply({review_id: review.review_id, password, confirmed: true,
    owner: 'owned-native-qualification'}));
  const restarted = new FirebirdDocker({root, execute});
  assert.deepEqual(await restarted.receipt(review.review_id), receipt);
  await assert.rejects(restarted.apply({review_id: review.review_id, password, confirmed: true,
    owner: 'owned-native-qualification'}));
  assert.ok(!calls.some(args => args.includes('rm')));
  const result = {passed: true, receipt, calls, consumed_review_refused: true,
    restart_receipt_preserved: true, automatic_resource_removal: false};
  assert.ok(!JSON.stringify(result).includes(password));
  await writeFile(output, JSON.stringify(result, null, 2) + '\n');
} else if (mode === 'isql') {
  const receipt = await launchIsql({...selected, password});
  assert.equal(receipt.state, 'process_started');
  assert.equal(receipt.native_connection_confirmed, false);
  assert.equal(receipt.transaction_outcome, 'owned-by-isql');
  await writeFile(output, JSON.stringify(receipt, null, 2) + '\n');
} else {
  throw new Error('Choose docker or isql qualification.');
}
