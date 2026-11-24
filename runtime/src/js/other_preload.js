/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

const { contextBridge, ipcRenderer } = require('electron/renderer');

contextBridge.exposeInMainWorld('electronUI', {
  getConfigData: (key) => ipcRenderer.invoke('getStoreData', key),
  setConfigData: (newValues) => ipcRenderer.invoke('setStoreData', newValues),
  showMessageBox: (options) => ipcRenderer.invoke('showMessageBox', options),
  restartApp: ()=>{ ipcRenderer.send('restartApp'); },
  getServerLogFile: ()=>ipcRenderer.invoke('getServerLogFile'),
  readServerLog: ()=>ipcRenderer.invoke('readServerLog'),
  checkPortAvailable: (port)=>ipcRenderer.invoke('checkPortAvailable', port),
  openConfigure: ()=>ipcRenderer.invoke('openConfigure'),
  getVaultStatus: () => ipcRenderer.invoke('desktop-vault:status'),
  unlockVault: (credentials) => ipcRenderer.invoke('desktop-vault:unlock', credentials),
  quitApp: () => ipcRenderer.send('desktop-vault:quit'),
  onServerReadyForLogin: (callback) => {
    ipcRenderer.removeAllListeners('desktop-vault:server-ready');
    ipcRenderer.on('desktop-vault:server-ready', (_event, details) => callback(details));
  },
});
