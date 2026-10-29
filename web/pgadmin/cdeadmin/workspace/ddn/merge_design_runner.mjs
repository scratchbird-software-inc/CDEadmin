import {Buffer} from 'node:buffer';
import {mergeDesign} from './merge_design.mjs';

process.stdin.setEncoding('utf8');
let input = '';
try {
  for await (const chunk of process.stdin) {
    input += chunk;
    if (Buffer.byteLength(input) > 25 * 1024 * 1024) throw new Error('Design request exceeds its limit');
  }
  const {baseline, draft, incoming} = JSON.parse(input);
  const snapshot = await mergeDesign(null, baseline, draft, incoming);
  const result = JSON.stringify(snapshot);
  if (Buffer.byteLength(result) > 8 * 1024 * 1024) throw new Error('Merged design exceeds 8 MiB');
  process.stdout.write(result);
} catch (error) {
  const message = String(error.message || 'Invalid or unsupported design');
  process.stdout.write(JSON.stringify({error: message.slice(0, 2048)}));
  process.exitCode = 1;
}
