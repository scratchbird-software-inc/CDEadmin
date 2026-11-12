import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { resolveAppPaths } from './appPaths.js';

test('resolveAppPaths preserves packaged Linux bundle paths when present', () => {
  const basePath = '/opt/cdeadmin/bin/resources/app/src/js';
  const existing = new Set([
    '/opt/cdeadmin/venv/bin/python3',
    '/opt/cdeadmin/web/CDEadmin.py',
  ]);
  const [pythonPath, webappPath] = resolveAppPaths(basePath, {
    osPlatform: 'linux',
    existsSync: (target) => existing.has(path.normalize(target)),
  });
  assert.equal(pythonPath, '/opt/cdeadmin/venv/bin/python3');
  assert.equal(webappPath, '/opt/cdeadmin/web/CDEadmin.py');
});

test('resolveAppPaths falls back to source checkout .venv and web/CDEadmin.py', () => {
  const repoRoot = '/home/dev/SandBox/CDEadmin';
  const basePath = path.join(repoRoot, 'runtime', 'src', 'js');
  const existing = new Set([
    path.join(repoRoot, '.venv', 'bin', 'python3'),
    path.join(repoRoot, 'web', 'CDEadmin.py'),
  ]);
  const [pythonPath, webappPath] = resolveAppPaths(basePath, {
    osPlatform: 'linux',
    existsSync: (target) => existing.has(path.normalize(target)),
  });
  assert.equal(pythonPath, path.join(repoRoot, '.venv', 'bin', 'python3'));
  assert.equal(webappPath, path.join(repoRoot, 'web', 'CDEadmin.py'));
});

test('resolveAppPaths honours Linux Flatpak paths', () => {
  const [pythonPath, webappPath] = resolveAppPaths('/app/CDEadmin/runtime/src/js', {
    osPlatform: 'linux',
    existsSync: (target) => target === '/.flatpak-info',
  });
  assert.equal(pythonPath, '/usr/bin/python');
  assert.equal(webappPath, '/app/CDEadmin/web/CDEadmin.py');
});
