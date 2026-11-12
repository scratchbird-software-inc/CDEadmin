/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import fs from 'fs';
import path from 'path';
import { platform } from 'os';

const insideFlatpak = (osPlatform, existsSync) => {
  return osPlatform === 'linux' && existsSync('/.flatpak-info');
};

const getSourcePythonCandidates = (repoRoot, osPlatform) => {
  if (osPlatform === 'win32' || osPlatform.startsWith('win')) {
    return [
      path.join(repoRoot, '.venv', 'Scripts', 'python.exe'),
      path.join(repoRoot, 'venv', 'Scripts', 'python.exe'),
      path.join(repoRoot, 'python', 'python.exe'),
    ];
  }
  return [
    path.join(repoRoot, '.venv', 'bin', 'python3'),
    path.join(repoRoot, '.venv', 'bin', 'python'),
    path.join(repoRoot, 'venv', 'bin', 'python3'),
    path.join(repoRoot, 'venv', 'bin', 'python'),
  ];
};

// Resolve the Python interpreter and canonical CDEadmin.py entry point for
// packaged builds as well as direct launches from a source checkout
// (where basePath is <repo>/runtime/src/js).
export const resolveAppPaths = (
  basePath,
  { osPlatform = platform(), existsSync = fs.existsSync } = {},
) => {
  let pythonRelPath;
  let webappRelPath;

  switch (osPlatform) {
  case 'win32':
    pythonRelPath = '../../../../../python/python.exe';
    webappRelPath = '../../../../../web/CDEadmin.py';
    break;
  case 'darwin':
    pythonRelPath = '../../../../Frameworks/Python.framework/Versions/Current/bin/python3';
    webappRelPath = '../../../web/CDEadmin.py';
    break;
  case 'linux':
    if (insideFlatpak(osPlatform, existsSync)) {
      return ['/usr/bin/python', '/app/CDEadmin/web/CDEadmin.py'];
    }
    pythonRelPath = '../../../../../venv/bin/python3';
    webappRelPath = '../../../../../web/CDEadmin.py';
    break;
  default:
    webappRelPath = '../../../web/CDEadmin.py';
    if (osPlatform.startsWith('win')) {
      pythonRelPath = '../python/python.exe';
    } else {
      pythonRelPath = '../venv/bin/python3';
    }
  }

  let resolvedPython = path.join(basePath, pythonRelPath);
  let resolvedWebapp = path.join(basePath, webappRelPath);

  const repoRoot = path.resolve(basePath, '../../..');
  if (!existsSync(resolvedWebapp)) {
    const sourceWebapp = path.join(repoRoot, 'web', 'CDEadmin.py');
    if (existsSync(sourceWebapp)) {
      resolvedWebapp = sourceWebapp;
    }
  }

  if (!existsSync(resolvedPython)) {
    const sourcePython = getSourcePythonCandidates(repoRoot, osPlatform)
      .find((candidate) => existsSync(candidate));
    if (sourcePython) {
      resolvedPython = sourcePython;
    }
  }

  return [resolvedPython, resolvedWebapp];
};
