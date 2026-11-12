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
import net from 'net';
import { app, session } from 'electron';
import { resolveAppPaths } from './appPaths.js';

let cdeadminServerProcess = null;

// This function is used to check whether directory is present or not
// if not present then create it recursively
const createDir = (dirName) => {
  if (!fs.existsSync(dirName)) {
    fs.mkdirSync(dirName, {recursive: true});
  }
};

// This function is used to get the python executable path
// based on the platform. Supports both packaged deployments and source checkouts.
export const getAppPaths = (basePath) => resolveAppPaths(basePath);

// This function is used to get the [local] app data path
// based on the platform. Use this for logs etc.
const getLocalAppDataPath = () => {
  let localAppDataPath = app.getPath('userData');
  if(process.platform == 'linux' && 'XDG_DATA_HOME' in process.env) {
    localAppDataPath = path.join(process.env.XDG_DATA_HOME, app.name);
  }

  // Create directory if not exists
  createDir(localAppDataPath);

  return localAppDataPath;
};

// This function is used to get the random available TCP port
// if fixedPort is set to 0. Else check whether port is in used or not.
export const getAvailablePort = (fixedPort) => {
  return new Promise(function(resolve, reject) {
    const server = net.createServer();

    server.listen(fixedPort, '127.0.0.1');

    server.on('error', (e) => {
      reject(e instanceof Error ? e : new Error(e.code));
    });

    server.on('listening', () => {
      let serverPort = server.address().port;
      server.close();
      resolve(serverPort);
    });
  });
};

// Get the app data folder path
const serverLogFile = path.join(
  getLocalAppDataPath(),
  'cdeadmin.' + (new Date()).getTime().toString() + '.log',
);

// This function is used to read the file and return the content
export const readServerLog = () => {
  if (fs.existsSync(serverLogFile)) {
    return fs.readFileSync(serverLogFile, 'utf8');
  }

  let errMsg = 'Unable to read file ' + serverLogFile + '.';
  console.warn(errMsg);
  return errMsg;
};

// This function is used to write the data into the log file
export const writeServerLog = (data) => {
  data = data + '\n';
  if (fs.existsSync(serverLogFile)) {
    fs.writeFileSync(serverLogFile, data, {flag: 'a+'});
  } else {
    fs.writeFileSync(serverLogFile, data, {flag: 'w'});
  }
};

// This function is used to remove the log file
const removeLogFile = () => {
  if (fs.existsSync(serverLogFile)) {
    fs.rmSync(serverLogFile);
  }
};

// Store the CDEadmin server-process object.
export const setProcessObject = (processObject) => {
  cdeadminServerProcess = processObject;
};

// This function is used to get the server log file.
export const getServerLogFile = () => {
  return serverLogFile;
};

// This function is used to kill the server process, remove the log files
// and quit the application.
export const cleanupAndQuitApp = () => {
  // Remove the server log file on exit
  removeLogFile();

  // Stop the CDEadmin server process when the application quits.
  if (cdeadminServerProcess != null) {
    try {
      process.kill(cdeadminServerProcess.pid);
    }
    catch (e) {
      console.warn('Failed to kill server process.', e);
    }
  }

  session.defaultSession.clearStorageData({
    storages: ['cookies', 'localstorage'],
  });
};
