/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {execSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..');
const webRoot = path.join(repoRoot, 'web');
const identityPath = path.join(
  webRoot,
  'pgadmin',
  'cdeadmin',
  'product',
  'product_identity.json'
);

let release = '0.325-alpha';
try {
  const identity = JSON.parse(fs.readFileSync(identityPath, 'utf8'));
  if (identity?.product?.version) {
    release = String(identity.product.version);
  }
} catch {
  // Fallback to default version string if identity file is unreadable
}

let commitHash = '';
let commitDate = '';
try {
  const out = execSync('git log -1 --format="%H %as"', {
    cwd: repoRoot,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'ignore'],
  }).trim();
  const [hash, date] = out.split(/\s+/, 2);
  commitHash = hash || '';
  commitDate = date || '';
} catch {
  // Non-git build environment
}

const now = new Date();
const builtAtUtc = now.toISOString().replace(/\.\d{3}Z$/, 'Z');
const tzOffsetMin = -now.getTimezoneOffset();
const sign = tzOffsetMin >= 0 ? '+' : '-';
const absMin = Math.abs(tzOffsetMin);
const pad = (n) => String(n).padStart(2, '0');
const builtAtLocal =
  `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ` +
  `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())} ` +
  `${sign}${pad(Math.floor(absMin / 60))}:${pad(absMin % 60)}`;

const payload = {
  release,
  commit_hash: commitHash,
  commit_short: commitHash ? commitHash.slice(0, 9) : '',
  commit_date: commitDate,
  built_at_utc: builtAtUtc,
  built_at_local: builtAtLocal,
};

fs.writeFileSync(
  path.join(webRoot, 'build_info.json'),
  JSON.stringify(payload, null, 2) + '\n',
  'utf8'
);
