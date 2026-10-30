/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import pgAdmin from 'sources/pgadmin';
import ConnectServerContent from './ConnectServerContent';
import url_for from 'sources/url_for';
import gettext from 'sources/gettext';
import current_user from 'pgadmin.user_management.current_user';

import getApiInstance from '../api_instance';
import MasterPasswordContent from './MasterPasswordContent';
import ChangePasswordContent from './ChangePasswordContent';
import NamedRestoreContent from './NamedRestoreContent';
import ChangeOwnershipContent from './ChangeOwnershipContent';
import UrlDialogContent from './UrlDialogContent';
import RenameTabContent from './RenameTabContent';
import { BROWSER_PANELS } from '../../../browser/static/js/constants';
import ErrorBoundary from '../helpers/ErrorBoundary';
import {createCloseGuardRegistry, ModalCloseGuardContext} from '../helpers/ModalCloseGuard';
import QuickSearch from '../QuickSearch';
import ProviderWorkspaceContent from './ProviderWorkspaceContent';
import MySQLPhysical from './MySQLPhysical';
import {activateSQLConnection, registerSQLConnection} from '../cdeadmin_ui/editors/SQLConnections';
import FirebirdMonitoring from './FirebirdMonitoring';
import PostgresqlMonitoring from './PostgresqlMonitoring';
import PostgresqlContinuity from './PostgresqlContinuity';
import DuckDBOperationReceipts from './DuckDBOperationReceipts';
import MySQLClone from './MySQLClone';
import MySQLHost from './MySQLHost';
import MySQLRouters from './MySQLRouters';
import MySQLWorkload from './MySQLWorkload';
import MySQLContentSearch from './MySQLContentSearch';
import MySQLDataDrift from './MySQLDataDrift';
import MySQLSpatial from './MySQLSpatial';
import MySQLBinlogArchives from './MySQLBinlogArchives';
import MySQLInstanceBackups from './MySQLInstanceBackups';
import MySQLInstanceRestores from './MySQLInstanceRestores';
import MySQLTopologies from './MySQLTopologies';
import MySQLSandboxes from './MySQLSandboxes';
import MySQLBinlogReplay from './MySQLBinlogReplay';
import SQLiteRecovery from './SQLiteRecovery';
import MySQLMonitoring from './MySQLMonitoring';
import FirebirdDocker from './FirebirdDocker';
import FirebirdDashboardEditor from './FirebirdDashboardEditor';
import endpointProfiles from 'pgadmin.cdeadmin.endpoint_profiles';
import FirebirdRegistration from './FirebirdRegistration';
import {invalidateProviderEndpointProfile} from
  'sources/cdeadmin_ui/navigation/providerDatabaseTree';

// This functions is used to show the connect server password dialog.
export function showServerPassword() {
  let title = arguments[0],
    formJson = arguments[1],
    nodeObj = arguments[2],
    nodeData = arguments[3],
    treeNodeInfo = arguments[4],
    itemNodeData = arguments[5],
    status = arguments[6],
    onSuccess = arguments[7],
    onFailure = arguments[8];

  pgAdmin.Browser.notifier.showModal(title, (onClose) => {
    return (
      <ConnectServerContent
        closeModal={()=>{
          onClose();
        }}
        data={formJson}
        onOK={(formData)=>{
          const api = getApiInstance();
          let _url = nodeObj.generate_url(itemNodeData, 'connect', nodeData, true);
          if (!status) {
            treeNodeInfo.setLeaf(itemNodeData);
            treeNodeInfo.removeIcon(itemNodeData);
            treeNodeInfo.addIcon(itemNodeData, {icon: 'icon-server-connecting'});
          }

          api.post(_url, formData)
            .then(res=>{
              onClose();
              return onSuccess(
                res.data, nodeObj, nodeData, treeNodeInfo, itemNodeData, status
              );
            })
            .catch((err)=>{
              return onFailure(
                err, null, nodeObj, nodeData, treeNodeInfo, itemNodeData, status
              );
            });
        }}
      />
    );
  }, {id: 'id-connect-server'});
}

// Verify a provider-managed endpoint without entering PostgreSQL connect code.
export function showEndpointVerification(
  title, nodeObj, nodeData, treeNodeInfo, itemNodeData, onSuccess, onFailure,
  databaseTargetId=null,
) {
  const api = getApiInstance();
  const endpointUrl = nodeObj.generate_url(
    itemNodeData, 'verify_endpoint', nodeData, true
  );
  const profile = endpointProfiles.get(nodeData.cde_profile_id);
  const prompt = {
    prompt_password: true,
    prompt_tunnel_password: false,
    username: nodeData.username,
    server_label: nodeData.label || nodeData._label,
    allow_save_password: current_user.allow_save_password,
    allow_user_override: profile?.route_kind === 'network',
    errmsg: null,
  };

  const submit = (formData, onClose) => {
    if (databaseTargetId) formData.set('database_target_id', databaseTargetId);
    return api.post(endpointUrl, formData)
      .then((res) => {
        onClose?.();
        onSuccess?.(res.data, nodeData, treeNodeInfo, itemNodeData);
      });
  };
  const showSecretPrompt = () => pgAdmin.Browser.notifier.showModal(
    title, (onClose) => (
      <ConnectServerContent
        closeModal={onClose}
        data={prompt}
        onOK={(formData) => submit(formData, onClose)
          .catch((error) => onFailure?.(error))}
      />
    ), {id: 'id-verify-endpoint'}
  );
  const verify = () => {
    // An explicit passwordless account (owner direction 2026-10-29) is
    // verified the same way: without a password, prompting only on 401.
    if (profile?.requires_secret === false || nodeData.cde_passwordless) {
    // Passwordless and conditionally-authenticated providers must first be
    // verified without fabricating a database password. If the retained
    // route activates an optional secret, the server responds with 401 and
    // the same provider endpoint can then request it explicitly.
      submit(new FormData())
        .catch((error) => {
          if (error?.response?.status === 401) {
            showSecretPrompt();
          } else {
            onFailure?.(error);
          }
        });
      return;
    }
    showSecretPrompt();
  };
  if (databaseTargetId && ['firebird-native', 'firebird-embedded'].includes(profile?.profile_id)) {
    return api.post(nodeObj.generate_url(itemNodeData, 'cde_workspace', nodeData, true),
      {action: 'database_target_list', request: {}}).then(response => {
      const target = response.data.data.targets.find(item => item.target_id === databaseTargetId);
      if (!target) throw new Error('Database registration is unavailable.');
      if (target.registration_credentials) prompt.username = target.registration_user;
      prompt.server_label = `${prompt.server_label} / ${target.display_name}`;
      return verify();
    }).catch(error => onFailure?.(error));
  }
  return verify();
}

let providerWorkspaceSequence = 0;

export function showFirebirdDashboardEditor(serverId, targetId) {
  const workspace = pgAdmin.Browser.docker.default_workspace;
  const panelId = `id-firebird-dashboard-editor-${++providerWorkspaceSequence}`;
  workspace.openTab({id: panelId, title: gettext('Firebird dashboard draft'),
    closable: true, manualClose: true, floatable: true,
    content: <ErrorBoundary><FirebirdDashboardEditor serverId={serverId}
      targetId={targetId} panelId={panelId} /></ErrorBoundary>,
  }, BROWSER_PANELS.MAIN, 'middle');
  return panelId;
}

export function showPostgresqlDashboardEditor(serverId, targetId) {
  const workspace = pgAdmin.Browser.docker.default_workspace;
  const panelId = `id-postgresql-dashboard-editor-${++providerWorkspaceSequence}`;
  workspace.openTab({id: panelId, title: gettext('PostgreSQL dashboard draft'),
    closable: true, manualClose: true, floatable: true,
    content: <ErrorBoundary><FirebirdDashboardEditor engine="postgresql" serverId={serverId}
      targetId={targetId} panelId={panelId} /></ErrorBoundary>,
  }, BROWSER_PANELS.MAIN, 'middle');
  return panelId;
}

export function showMySQLDashboardEditor(serverId, targetId, engine='mysql') {
  const panelId = `id-${engine}-dashboard-editor-${++providerWorkspaceSequence}`;
  pgAdmin.Browser.docker.default_workspace.openTab({id: panelId, title: engine === 'mariadb' ? gettext('MariaDB dashboard draft') : engine === 'duckdb' ? gettext('DuckDB dashboard draft') : engine === 'sqlite' ? gettext('SQLite dashboard draft') : gettext('MySQL dashboard draft'),
    closable: true, manualClose: true, floatable: true,
    content: <ErrorBoundary><FirebirdDashboardEditor engine={engine} serverId={serverId}
      targetId={targetId} panelId={panelId} /></ErrorBoundary>,
  }, BROWSER_PANELS.MAIN, 'middle');
  return panelId;
}

export function showMySQLMonitor(serverId, targetId, name='MySQL', engine='mysql') {
  const panelId = `id-${engine}-monitor-${serverId}-${targetId || 'server'}`;
  pgAdmin.Browser.docker.default_workspace.openTab({id: panelId, title: `${name} — dashboard`,
    closable: true, floatable: true,
    content: <ErrorBoundary><MySQLMonitoring engine={engine} serverId={Number(serverId)} targetId={targetId} /></ErrorBoundary>,
  }, BROWSER_PANELS.MAIN, 'middle');
  return panelId;
}

export function showMySQLFleet(engine='mysql') {
  const panelId = `id-${engine}-fleet`;
  pgAdmin.Browser.docker.default_workspace.openTab({id: panelId, title: engine === 'mariadb' ? gettext('MariaDB engine dashboard') : engine === 'duckdb' ? gettext('DuckDB engine dashboard') : engine === 'sqlite' ? gettext('SQLite engine dashboard') : gettext('MySQL engine dashboard'),
    closable: true, floatable: true,
    content: <ErrorBoundary><MySQLMonitoring engine={engine} engineMode onNavigate={(sid, target, name) => showMySQLMonitor(sid, target, name, engine)} /></ErrorBoundary>,
  }, BROWSER_PANELS.MAIN, 'middle');
  return panelId;
}

export function showPostgresqlFleet() {
  const panelId = 'id-postgresql-fleet';
  pgAdmin.Browser.docker.default_workspace.openTab({id: panelId,
    title: gettext('PostgreSQL engine dashboard'), closable: true, floatable: true,
    content: <ErrorBoundary><PostgresqlMonitoring engineMode onNavigate={showPostgresqlMonitor} /></ErrorBoundary>,
  }, BROWSER_PANELS.MAIN, 'middle');
  return panelId;
}

export function showPostgresqlMonitor(serverId, targetId, name='PostgreSQL', policyMode=false) {
  const panelId = `id-postgresql-monitor-${serverId}-${targetId || 'server'}-${policyMode ? 'policy' : 'viewer'}`;
  pgAdmin.Browser.docker.default_workspace.openTab({id: panelId,
    title: `${name} — ${policyMode ? 'monitoring settings' : 'dashboard'}`, closable: true, floatable: true,
    content: <ErrorBoundary><PostgresqlMonitoring serverId={Number(serverId)} targetId={targetId}
      policyMode={policyMode} /></ErrorBoundary>,
  }, BROWSER_PANELS.MAIN, 'middle');
  return panelId;
}

export function showFirebirdMonitor(serverId, targetId, name='Firebird') {
  const workspace = pgAdmin.Browser.docker.default_workspace;
  const panelId = `id-firebird-monitor-${serverId}-${targetId || 'server'}`;
  workspace.openTab({id: panelId, title: `${name} — dashboard`, closable: true, floatable: true,
    content: <ErrorBoundary><FirebirdMonitoring serverId={serverId} targetId={targetId}
      onNavigate={showFirebirdMonitor} /></ErrorBoundary>,
  }, BROWSER_PANELS.MAIN, 'middle');
  return panelId;
}

export function showFirebirdDocker(onRegister) {
  const workspace = pgAdmin.Browser.docker.default_workspace;
  const panelId = `id-firebird-docker-${++providerWorkspaceSequence}`;
  workspace.openTab({id: panelId, title: gettext('Provision Firebird in Docker'),
    closable: true, floatable: true,
    content: <ErrorBoundary><FirebirdDocker onRegister={onRegister} /></ErrorBoundary>,
  }, BROWSER_PANELS.MAIN, 'middle');
  return panelId;
}

export function showFirebirdFleet() {
  const workspace = pgAdmin.Browser.docker.default_workspace;
  const panelId = 'id-firebird-fleet-dashboard';
  workspace.openTab({id: panelId, title: gettext('Firebird engine dashboard'),
    closable: true, floatable: true,
    content: <ErrorBoundary><FirebirdMonitoring engineMode onNavigate={showFirebirdMonitor} /></ErrorBoundary>,
  }, BROWSER_PANELS.MAIN, 'middle');
  return panelId;
}

export function showProviderWorkspace(
  title, nodeObj, nodeData, itemNodeData, initialTab='resources',
  initialContext={}, onEndpointRemoved, registerOnly=false,
) {
  const generatedUrl = nodeObj.generate_url(
    itemNodeData, 'cde_workspace', nodeData, true
  );
  const parameters = new URLSearchParams();
  const databaseTargetId = initialContext.database_target_id || (
    initialContext.resource_kind &&
    initialContext.resource_kind !== 'database' ? null :
      (initialContext.resource_id || null)
  );
  if (databaseTargetId) {
    parameters.set('database_target_id', databaseTargetId);
  }
  if (initialContext.resource_kind === 'database' &&
      initialContext.operation_id) {
    parameters.set('focused_operation_id', initialContext.operation_id);
  }
  const endpointUrl = parameters.size ?
    `${generatedUrl}${generatedUrl.includes('?') ? '&' : '?'}${parameters}` :
    generatedUrl;
  const connection = {id: endpointUrl, serverId: nodeData._id, databaseTargetId,
    engine: endpointProfiles.get(nodeData.cde_profile_id)?.display_name ||
      nodeData.cde_engine_id || nodeData.engine_id || (nodeData.cde_endpoint ? 'Unknown engine' : 'PostgreSQL'),
    label: `${nodeData.label || nodeData._label || title} / ${initialContext.display_name || databaseTargetId || 'server'}`};
  if (registerOnly) {
    registerSQLConnection({...connection, open: () => showProviderWorkspace(
      title, nodeObj, nodeData, itemNodeData, 'studio', initialContext, onEndpointRemoved)});
    return;
  }
  const workspace = pgAdmin.Browser.docker.default_workspace;
  const panelId = `id-provider-workspace-${++providerWorkspaceSequence}`;
  const closeGuards = createCloseGuardRegistry();
  const onClose = () => workspace.close(panelId);
  const recoveryTargetRegistered = () => {
    const tree = pgAdmin.Browser.tree;
    const parent = tree.parent(itemNodeData);
    const connector = pgAdmin.Browser.Nodes[tree.itemData(parent)?._type];
    connector?.callbacks?.refresh?.call(connector, null, parent);
  };
  const serverTool=initialTab==='mysql-routers' ? <MySQLRouters post={payload => getApiInstance().post(endpointUrl,payload).then(response => response.data.data)} /> : initialTab==='mysql-physical' ? <MySQLPhysical onTargetRegistered={recoveryTargetRegistered} post={payload => getApiInstance().post(endpointUrl,payload).then(response => response.data.data)} /> : initialTab==='mysql-spatial' ? <MySQLSpatial databaseTargetId={databaseTargetId} post={payload => getApiInstance().post(endpointUrl,payload).then(response => response.data.data)} /> : initialTab==='mysql-data-drift' ? <MySQLDataDrift databaseTargetId={databaseTargetId} post={payload => getApiInstance().post(endpointUrl,payload).then(response => response.data.data)} /> : initialTab==='mysql-content-search' ? <MySQLContentSearch databaseTargetId={databaseTargetId} post={payload => getApiInstance().post(endpointUrl,payload).then(response => response.data.data)} /> : initialTab==='mysql-workload' ? <MySQLWorkload databaseTargetId={databaseTargetId} post={payload => getApiInstance().post(endpointUrl,payload).then(response => response.data.data)} /> : initialTab==='mysql-sandboxes' ? <MySQLSandboxes post={payload => getApiInstance().post(endpointUrl,payload).then(response => response.data.data)} /> : initialTab==='mysql-topologies' ? <MySQLTopologies post={payload => getApiInstance().post(endpointUrl,payload).then(response => response.data.data)} /> : initialTab==='mysql-instance-restores' ? <MySQLInstanceRestores post={payload => getApiInstance().post(endpointUrl,payload).then(response => response.data.data)} /> : initialTab==='mysql-instance-backups' ? <MySQLInstanceBackups endpointUrl={endpointUrl} post={payload => getApiInstance().post(endpointUrl,payload).then(response => response.data.data)} /> : initialTab==='mysql-host' ? <MySQLHost post={payload => getApiInstance().post(endpointUrl,payload).then(response => response.data.data)} /> : initialTab==='duckdb-session-receipts' ? <DuckDBOperationReceipts databaseTargetId={databaseTargetId}
    post={payload => getApiInstance().post(endpointUrl,payload).then(response => response.data.data)} /> : initialTab==='sqlite-recovery' ? <SQLiteRecovery databaseTargetId={databaseTargetId}
    onTargetCatalogChanged={() => nodeObj.callbacks.refresh.call(nodeObj,null,itemNodeData)}
    post={payload => getApiInstance().post(endpointUrl,payload).then(response => response.data.data)} /> : ['mysql-binlog-replay','mariadb-binlog-replay'].includes(initialTab) ?
    <MySQLBinlogReplay engine={initialTab==='mariadb-binlog-replay' ? 'mariadb' : 'mysql'} post={payload => getApiInstance().post(endpointUrl,payload).then(response => response.data.data)} /> : ['mysql-binlogs','mariadb-binlogs','mysql-raw-binlogs'].includes(initialTab) ?
      <MySQLBinlogArchives raw={initialTab==='mysql-raw-binlogs'} engine={initialTab==='mariadb-binlogs' ? 'mariadb' : 'mysql'} endpointUrl={endpointUrl} post={payload => getApiInstance().post(endpointUrl,payload).then(response => response.data.data)} /> : initialTab === 'mysql-clone' ?
        <MySQLClone post={payload => getApiInstance().post(endpointUrl,payload).then(response => response.data.data)} /> : initialTab === 'postgresql-continuity' ?
          <PostgresqlContinuity endpointUrl={endpointUrl} post={payload => getApiInstance().post(endpointUrl,payload).then(response => response.data.data)} /> : null;
  const panel = {
    id: panelId,
    beforeClose: closeGuards.beforeClose,
    title,
    closable: true,
    floatable: true,
    content: <ModalCloseGuardContext.Provider value={closeGuards.register}><ErrorBoundary>{serverTool || (initialTab === 'firebird-registration' ?
      <FirebirdRegistration targetId={databaseTargetId} operation={initialContext.registration_operation}
        post={payload => getApiInstance().post(endpointUrl, payload).then(response => response.data.data)
          .catch(error => {throw new Error(error?.response?.data?.errormsg || error.message);})}
        onChanged={() => {
          const tree = pgAdmin.Browser.tree;
          const connector = tree.parent(itemNodeData);
          const node = pgAdmin.Browser.Nodes[tree.itemData(connector)?._type];
          node?.callbacks?.refresh?.call(node, null, connector);
        }} /> : ['monitoring', 'monitoring_policy'].includes(initialTab) ?
        (['mysql-native', 'mariadb-native', 'duckdb-native', 'sqlite-native'].includes(nodeData.cde_profile_id) ? <MySQLMonitoring engine={nodeData.cde_profile_id === 'mariadb-native' ? 'mariadb' : nodeData.cde_profile_id === 'duckdb-native' ? 'duckdb' : nodeData.cde_profile_id === 'sqlite-native' ? 'sqlite' : 'mysql'} serverId={Number(nodeData._id ?? nodeData.id)}
          targetId={databaseTargetId} policyMode={initialTab === 'monitoring_policy'} /> :
          <FirebirdMonitoring onNavigate={showFirebirdMonitor} serverId={Number(nodeData._id ?? nodeData.id)}
            targetId={databaseTargetId} policyMode={initialTab === 'monitoring_policy'} />) : <ProviderWorkspaceContent
          closeModal={onClose}
          endpointUrl={endpointUrl}
          initialTab={initialTab}
          initialContext={initialContext}
          onTargetCatalogChanged={() => {
            nodeObj.callbacks.refresh.call(nodeObj, null, itemNodeData);
          }}
          onRecreateEmpty={(databasePath) => {
            showProviderWorkspace(
              gettext('Create empty Firebird database'), nodeObj, nodeData,
              itemNodeData, 'connections', {
                database_mode: 'create', recreate_empty_path: databasePath,
              }
            );
            onClose();
          }}
          onOpenSearchResult={(targetId, resource) => showProviderWorkspace(
            resource.display_name, nodeObj, nodeData, itemNodeData, 'object', {
              database_target_id: targetId, resource_id: resource.resource_id,
              resource_kind: resource.resource_kind, operation_id: 'inspect',
            })}
          onEndpointRemoved={onEndpointRemoved}
          onEndpointProfileSaved={(result) => invalidateProviderEndpointProfile(
            pgAdmin.Browser.tree, itemNodeData, result
          )}
          onCredentialRequired={(retry)=>{
            nodeObj.callbacks.verify_cde_endpoint.call(nodeObj, {
              item: itemNodeData,
              databaseTargetId,
              onSuccess: retry,
            });
          }}
        />)}</ErrorBoundary></ModalCloseGuardContext.Provider>,
  };
  if (initialTab === 'studio') {
    activateSQLConnection({...connection, content: panel.content});
    workspace.focus(BROWSER_PANELS.SQL);
    return BROWSER_PANELS.SQL;
  }
  workspace.openTab(panel, BROWSER_PANELS.MAIN, 'middle');
  return panelId;
}

function masterPassCallbacks(masterpass_callback_queue) {
  while(masterpass_callback_queue.length > 0) {
    let callback = masterpass_callback_queue.shift();
    callback();
  }
}

export function checkMasterPassword(data, masterpass_callback_queue, cancel_callback) {
  const api = getApiInstance();
  api.post(url_for('browser.set_master_password'), data).then((res)=> {
    let isKeyring = res.data.data.keyring_name.length > 0;
    let error = res.data.data.errmsg;

    if(!res.data.data.present) {
      showMasterPassword(res.data.data.reset, res.data.data.errmsg, masterpass_callback_queue, cancel_callback, res.data.data.keyring_name, res.data.data.master_password_hook);
    } else {
      masterPassCallbacks(masterpass_callback_queue);
      if(isKeyring) {
        if(error){
          pgAdmin.Browser.notifier.alertText(gettext('Migration failed'),
            gettext(`Passwords previously saved cannot be re-encrypted using the encryption key stored in the ${res.data.data.keyring_name} due to ${error}.`));
        }else{
          pgAdmin.Browser.notifier.alertText(gettext('Migration successful'),
            gettext(`Passwords previously saved are re-encrypted using encryption key stored in the ${res.data.data.keyring_name}.`));
        }
      }
    }
  }).catch(function(error) {
    pgAdmin.Browser.notifier.pgRespErrorNotify(error);
  });
}

// This functions is used to show the master password dialog.
export function showMasterPassword(isPWDPresent, errmsg, masterpass_callback_queue, cancel_callback, keyring_name='', master_password_hook='') {
  const api = getApiInstance();
  let title =  gettext('Set Master Password');
  if (keyring_name.length > 0)
    title = gettext('Migrate Saved Passwords');
  else if (isPWDPresent)
    title = gettext('Unlock Saved Passwords');

  if(master_password_hook){
    if(errmsg){
      pgAdmin.Browser.notifier.errorText(errmsg);
      return true;
    }else{
      pgAdmin.Browser.notifier.confirm(gettext('Reset Master Password'),
        gettext('The master password retrieved from the master password hook utility is different from what was previously retrieved.') + '<br>'
            + gettext('Do you want to reset your master password to match?') + '<br><br>'
            + gettext('Note that this will close all open database connections and remove all saved passwords.'),
        function() {
          let _url = url_for('browser.reset_master_password');
          const api = getApiInstance();
          api.delete(_url)
            .then(() => {
              pgAdmin.Browser.notifier.info('The master password has been reset.');
            })
            .catch((err) => {
              pgAdmin.Browser.notifier.errorText(err.message);
            });
          return true;
        },
        function() {/* If user clicks No */ return true;}
      );}
  }else{

    pgAdmin.Browser.notifier.showModal(title, (onClose)=> {
      return (
        <MasterPasswordContent
          isPWDPresent= {isPWDPresent}
          data={{'errmsg': errmsg}}
          keyringName={keyring_name}
          closeModal={() => {
            onClose();
          }}
          onResetPassowrd={(isKeyRing=false)=>{
            pgAdmin.Browser.notifier.confirm(gettext('Reset Master Password'),
              gettext('This will remove all the saved passwords. This will also remove established connections to '
            + 'the server and you may need to reconnect again. Do you wish to continue?'),
              function() {
                let _url = url_for('browser.reset_master_password');

                api.delete(_url)
                  .then(() => {
                    onClose();
                    if(!isKeyRing) {
                      showMasterPassword(false, null, masterpass_callback_queue, cancel_callback);
                    }
                  })
                  .catch((err) => {
                    pgAdmin.Browser.notifier.errorText(err.message);
                  });
                return true;
              },
              function() {/* If user clicks No */ return true;}
            );
          }}
          onCancel={()=>{
            cancel_callback?.();
          }}
          onOK={(formData) => {
            onClose();
            checkMasterPassword(formData, masterpass_callback_queue, cancel_callback);
          }}
        />
      );
    }, {id: 'id-master-password'});
  }
}

export function showChangeServerPassword() {
  let title = arguments[0],
    nodeData = arguments[1],
    nodeObj = arguments[2],
    itemNodeData = arguments[3],
    isPgPassFileUsed = arguments[4];

  const panelId = BROWSER_PANELS.SEARCH_OBJECTS;
  const onClose = ()=>{pgAdmin.Browser.docker.default_workspace.close(panelId);};
  pgAdmin.Browser.docker.default_workspace.openDialog({
    id: panelId,
    title: title,
    content: (
      <ChangePasswordContent
        onClose={onClose}
        onSave={(isNew, data)=>{
          return new Promise((resolve, reject)=>{
            const api = getApiInstance();
            let _url = nodeObj.generate_url(itemNodeData, 'change_password', nodeData, true);

            api.post(_url, data)
              .then(({data: respData})=>{
                pgAdmin.Browser.notifier.success(respData.info);
                // Notify user to update pgpass file
                if(isPgPassFileUsed) {
                  pgAdmin.Browser.notifier.alert(
                    gettext('Change Password'),
                    gettext('Please make sure to disconnect the server'
                    + ' and update the new password in the pgpass file'
                      + ' before performing any other operation')
                  );
                }

                resolve(respData.data);
                onClose();
              })
              .catch((error)=>{
                reject(error instanceof Error ? error : Error(gettext('Something went wrong')));
              });
          });
        }}
        userName={nodeData.user.name}
        isPgpassFileUsed={isPgPassFileUsed}
      />
    )
  }, pgAdmin.Browser.stdW.md, pgAdmin.Browser.stdH.md);
}

export function showChangeUserPassword(url) {
  const title = gettext('Change CDEadmin User Password');
  pgAdmin.Browser.notifier.showModal(title, (onClose) => {
    return <ChangePasswordContent
      getInitData={()=>{
        const api = getApiInstance();
        return new Promise((resolve, reject)=>{
          api.get(url)
            .then((res)=>{
              resolve(res.data);
            })
            .catch((err)=>{
              reject(err instanceof Error ? err : Error(gettext('Something went wrong')));
            });
        });
      }}
      onClose={()=>{
        onClose();
      }}
      onSave={(_isNew, data)=>{
        const api = getApiInstance();
        return new Promise((resolve, reject)=>{
          const formData =  {
            'password': data.password,
            'new_password': data.newPassword,
            'new_password_confirm': data.confirmPassword,
            'csrf_token': data.csrf_token
          };

          api({
            method: 'POST',
            url: url,
            data: formData,
          }).then((res)=>{
            resolve(res.data.info);
            onClose();
            pgAdmin.Browser.notifier.success(res.data.info);
          }).catch((err)=>{
            reject(err instanceof Error ? err : Error(gettext('Something went wrong')));
          });
        });
      }}
      hasCsrfToken={true}
      showUser={false}
    />;
  },
  { isFullScreen: false, isResizeable: true, showFullScreen: false, isFullWidth: true,
    dialogWidth: pgAdmin.Browser.stdW.md, dialogHeight: pgAdmin.Browser.stdH.md, id: 'id-change-password'});
}

export function showNamedRestorePoint() {
  let title = arguments[0],
    nodeData = arguments[1],
    nodeObj = arguments[2],
    itemNodeData = arguments[3];

  const panelId = BROWSER_PANELS.SEARCH_OBJECTS;
  const onClose = ()=>{pgAdmin.Browser.docker.default_workspace.close(panelId);};
  pgAdmin.Browser.docker.default_workspace.openDialog({
    id: panelId,
    title: title,
    content: (
      <NamedRestoreContent
        closeModal={onClose}
        onOK={(formData)=>{
          const api = getApiInstance();
          let _url = nodeObj.generate_url(itemNodeData, 'restore_point', nodeData, true);

          api.post(_url, formData)
            .then(res=>{
              onClose();
              pgAdmin.Browser.notifier.success(res.data.data.result);
            })
            .catch(function(error) {
              pgAdmin.Browser.notifier.pgRespErrorNotify(error);
            });
        }}
      />
    )
  }, pgAdmin.Browser.stdW.md, 180);
}

export function showChangeOwnership() {
  let title = arguments[0],
    userList = arguments[1],
    noOfSharedServers = arguments[2],
    deletedUser = arguments[3],
    deleteUserRow = arguments[4];

  // Render Preferences component
  pgAdmin.Browser.notifier.showModal(title, (onClose) => {
    return <ChangeOwnershipContent
      onClose={()=>{
        onClose();
      }}
      onSave={(isNew, data)=>{
        const api = getApiInstance();

        return new Promise((resolve, reject)=>{
          if (data.newUser == '') {
            deleteUserRow();
            onClose();
          } else {
            let newData = {'new_owner': `${data.newUser}`, 'old_owner': `${deletedUser['id']}`};
            api.post(url_for('user_management.change_owner'), newData)
              .then(({data: respData})=>{
                pgAdmin.Browser.notifier.success(gettext(respData.info));
                onClose();
                deleteUserRow();
                resolve(respData.data);
              })
              .catch((err)=>{
                reject(err instanceof Error ? err : Error(gettext('Something went wrong')));
              });
          }
        });
      }}
      userList = {userList}
      noOfSharedServers = {noOfSharedServers}
      deletedUser = {deletedUser['name']}
    />;
  },
  { isFullScreen: false, isResizeable: true, showFullScreen: true, isFullWidth: true,
    dialogWidth: pgAdmin.Browser.stdW.md, dialogHeight: pgAdmin.Browser.stdH.md, id: 'id-change-owner' });
}

export function showUrlDialog() {
  let title = arguments[0],
    url = arguments[1],
    helpFile = arguments[2],
    width = arguments[3],
    height = arguments[4];

  pgAdmin.Browser.notifier.showModal(title, (onClose) => {
    return <UrlDialogContent url={url} helpFile={helpFile} onClose={onClose} />;
  },
  { isFullScreen: false, isResizeable: true, showFullScreen: true, isFullWidth: true,
    dialogWidth: width || pgAdmin.Browser.stdW.md, dialogHeight: height || pgAdmin.Browser.stdH.md});
}

export function showRenameTab(panelId, panelDocker) {
  pgAdmin.Browser.notifier.showModal(gettext('Rename Tab'), (onClose) => {
    return (
      <ErrorBoundary>
        <RenameTabContent
          closeModal={()=>{
            onClose();
          }}
          panelId={panelId}
          panelDocker={panelDocker}
        />
      </ErrorBoundary>
    );
  });
}

export function showQuickSearch() {
  pgAdmin.Browser.notifier.showModal(gettext('Quick Search'), (closeModal) => {
    return <QuickSearch closeModal={closeModal}/>;
  },
  { isFullScreen: false, isResizeable: false, showFullScreen: false, isFullWidth: false, showTitle: false, id: 'id-quick-search'}
  );
}
