/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import { useEffect, useState } from 'react';
import { styled } from '@mui/material/styles';
import CollectionNodeProperties from './CollectionNodeProperties';
import ErrorBoundary from '../../static/js/helpers/ErrorBoundary';
import withStandardTabInfo from '../../static/js/helpers/withStandardTabInfo';
import { BROWSER_PANELS } from '../../browser/static/js/constants';
import { generateNodeUrl } from '../../browser/static/js/node_ajax';
import {
  LEGACY_REGISTRATION_RETIRED,
  LIFECYCLE_EDIT_ENGINES,
  refreshConnectorAfterServerSave,
} from '../../browser/static/js/ProviderObjectEditor';
import { canLaunchServerMenu, providerContextMenuItems } from '../../browser/static/js/ProviderContextMenu';
import ObjectNodeProperties from './ObjectNodeProperties';
import EmptyPanelMessage from '../../static/js/components/EmptyPanelMessage';
import getApiInstance from 'sources/api_instance';
import gettext from 'sources/gettext';
import endpointProfiles from 'pgadmin.cdeadmin.endpoint_profiles';
import { Banner, Button } from 'sources/cdeadmin_ui';
import { ServerRegistrationHost } from '../../static/js/cdeadmin_ui/objects';
import { Box } from '@mui/material';
import { usePgAdmin } from '../../static/js/PgAdminProvider';
import PropTypes from 'prop-types';
import _ from 'lodash';
import ProviderObjectProperties from './ProviderObjectProperties';

const StyledBox = styled(Box)(({theme}) => ({
  height: '100%',
  background: theme.otherVars.emptySpaceBg,
  display: 'flex',
  flexDirection: 'column'
}));

function resolveServerGroupTarget(pgAdmin, nodeItem) {
  const tree = pgAdmin?.Browser?.tree;
  if (!tree) return {item: null, data: null, hierarchy: null};
  let cur = nodeItem;
  while (cur && tree.itemData?.(cur)?._type !== 'server_group') {
    cur = tree.hasParent?.(cur) ? tree.parent(cur) : null;
  }
  if (!cur) {
    const roots = tree.children?.() || [];
    cur = roots.find((c) => tree.itemData?.(c)?._type === 'server_group') || roots[0] || null;
  }
  if (!cur) return {item: null, data: null, hierarchy: null};
  return {
    item: cur,
    data: tree.itemData?.(cur),
    hierarchy: tree.getTreeNodeHierarchy?.(cur),
  };
}

function ConnectorRegistrationProperties({nodeData, nodeItem}) {
  const pgAdmin = usePgAdmin();
  const rawEngineId = nodeData?.engine_id || nodeData?._id || '';
  const engineId = rawEngineId === 'opensearch_sql_ppl' ? 'opensearch' : rawEngineId;
  const profiles = endpointProfiles?.interfaces?.(engineId) || [];
  const [selectedProfileId, setSelectedProfileId] = useState(null);
  const [intent, setIntent] = useState('endpoint');
  const [formIteration, setFormIteration] = useState(0);

  if (!profiles.length) {
    return (
      <Box sx={{my: '4px', width: '100%', minWidth: 0}}>
        <EmptyPanelMessage text={gettext('No registration profile is available for this connector.')} />
      </Box>
    );
  }

  const profile =
    profiles.find((p) => p.profile_id === selectedProfileId) || profiles[0];
  const networkSupportsDatabaseIntent = Boolean(
    profile.route_kind !== 'embedded_file' && profile.database_targeting?.multiple
  );
  const networkSupportsCreateIntent = Boolean(
    networkSupportsDatabaseIntent && profile.database_targeting?.create_and_activate
  );
  const activeIntent =
    profile.route_kind === 'embedded_file' && intent === 'endpoint'
      ? 'register_existing'
      : profile.route_kind !== 'embedded_file' && !networkSupportsDatabaseIntent && intent !== 'endpoint'
        ? 'endpoint'
        : profile.route_kind !== 'embedded_file' && intent === 'create_database' && !networkSupportsCreateIntent
          ? 'endpoint'
          : intent;

  const api = getApiInstance();
  const serverNode = pgAdmin?.Browser?.Nodes?.server;
  const groupTarget = resolveServerGroupTarget(pgAdmin, nodeItem);
  const baseUrl =
    serverNode && groupTarget.hierarchy && groupTarget.data
      ? generateNodeUrl.call(
        serverNode,
        groupTarget.hierarchy,
        'create',
        groupTarget.data,
        false,
        serverNode.url_jump_after_node
      )
      : '/browser/server/obj/1/';
  const urlFor = () => baseUrl;

  const displayLabel = profile.engine_display_name || profile.display_name || engineId;
  const intentTitles = {
    create_database: gettext('Create %s database', displayLabel),
    register_existing: gettext('Register existing %s database', displayLabel),
    endpoint: gettext('Register %s server / instance', displayLabel),
  };
  const initialData = {
    name: gettext('%s on localhost', displayLabel),
    cde_profile_id: profile.profile_id,
    cde_registration_intent: activeIntent,
    host: profile.route_kind === 'network' ? 'localhost' : '',
    port: profile.default_port,
    db: '',
    connect_now: false,
  };

  const onSaved = (response) => {
    setTimeout(() => serverNode?.clear_cache?.(groupTarget.item), 0);
    const createdId = response?.node?._id ?? response?.node?.id;
    void refreshConnectorAfterServerSave(
      profile.engine_id,
      groupTarget.item,
      createdId
    ).then((refreshed) => {
      if (!refreshed && response?.node && groupTarget.hierarchy) {
        pgAdmin?.Browser?.Events?.trigger?.(
          'pgadmin:browser:tree:add',
          {...response.node},
          {...groupTarget.hierarchy}
        );
      }
      setFormIteration((n) => n + 1);
    });
    pgAdmin?.Browser?.notifier?.success?.(gettext('Server registered.'));
  };

  return (
    <Box
      data-cdeadmin-qa-key={`connector-registration-panel-${engineId}`}
      sx={{height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column'}}
    >
      <Box
        sx={{
          px: 3,
          py: 1,
          borderBottom: '1px solid',
          borderColor: 'divider',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 1,
          flexWrap: 'wrap',
        }}
      >
        <Box sx={{display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap'}}>
          {profiles.length > 1 &&
            profiles.map((candidate) => {
              const baseLabel = candidate.interface_display_name || candidate.display_name;
              const label =
                candidate.route_kind === 'embedded_file'
                  ? gettext('%s (This computer)', baseLabel)
                  : gettext('%s (Server)', baseLabel);
              return (
                <Button
                  key={candidate.profile_id}
                  size="small"
                  intent={candidate.profile_id === profile.profile_id ? 'primary' : 'neutral'}
                  onClick={() => setSelectedProfileId(candidate.profile_id)}
                >
                  {label}
                </Button>
              );
            })}
          {profile.route_kind === 'embedded_file' && (
            <>
              <Button
                size="small"
                intent={activeIntent === 'register_existing' ? 'primary' : 'neutral'}
                onClick={() => setIntent('register_existing')}
              >
                {gettext('Open Existing File')}
              </Button>
              <Button
                size="small"
                intent={activeIntent === 'create_database' ? 'primary' : 'neutral'}
                onClick={() => setIntent('create_database')}
              >
                {gettext('Create New File')}
              </Button>
            </>
          )}
          {networkSupportsDatabaseIntent && (
            <>
              <Button
                size="small"
                intent={activeIntent === 'endpoint' ? 'primary' : 'neutral'}
                onClick={() => setIntent('endpoint')}
              >
                {gettext('Register Server')}
              </Button>
              <Button
                size="small"
                intent={activeIntent === 'register_existing' ? 'primary' : 'neutral'}
                onClick={() => setIntent('register_existing')}
              >
                {gettext('Register Existing Database')}
              </Button>
              {networkSupportsCreateIntent && (
                <Button
                  size="small"
                  intent={activeIntent === 'create_database' ? 'primary' : 'neutral'}
                  onClick={() => setIntent('create_database')}
                >
                  {gettext('Create Database')}
                </Button>
              )}
            </>
          )}
        </Box>
        <Button
          size="small"
          intent="neutral"
          data-cdeadmin-qa-key="connector-open-registration-tab"
          onClick={() =>
            serverNode?.callbacks?.register_engine_server?.call(serverNode, {
              item: nodeItem,
              engineId,
              registrationContext: {
                profile_id: profile.profile_id,
                registration_intent: activeIntent,
              },
            })
          }
        >
          {gettext('Open in Separate Tab…')}
        </Button>
      </Box>
      <Box sx={{flex: 1, minHeight: 0}}>
        <ServerRegistrationHost
          key={`${profile.profile_id}-${activeIntent}-${formIteration}`}
          api={api}
          engine={profile.engine_id}
          mode="create"
          urlFor={urlFor}
          initialData={initialData}
          profileId={profile.profile_id}
          intent={activeIntent}
          verifyNow="auto"
          displayName={intentTitles[activeIntent] || intentTitles.endpoint}
          onSaved={onSaved}
        />
      </Box>
    </Box>
  );
}

ConnectorRegistrationProperties.propTypes = {
  nodeData: PropTypes.object,
  nodeItem: PropTypes.object,
};

function LocalhostServerProperties({nodeData, nodeItem}) {
  const pgAdmin = usePgAdmin();
  const rawEngineId = nodeData?.engine_id || nodeData?._id || '';
  const engineId = rawEngineId === 'opensearch_sql_ppl' ? 'opensearch' : rawEngineId;
  const profiles = endpointProfiles?.interfaces?.(engineId) || [];
  const profile =
    profiles.find((p) => p.route_kind === 'network') || profiles[0];
  const [formIteration, setFormIteration] = useState(0);

  if (!profile) {
    return (
      <Box sx={{my: '4px', width: '100%', minWidth: 0}}>
        <EmptyPanelMessage text={gettext('No server profile is available for this localhost entry.')} />
      </Box>
    );
  }

  const api = getApiInstance();
  const serverNode = pgAdmin?.Browser?.Nodes?.server;
  const groupTarget = resolveServerGroupTarget(pgAdmin, nodeItem);
  const baseUrl =
    serverNode && groupTarget.hierarchy && groupTarget.data
      ? generateNodeUrl.call(
        serverNode,
        groupTarget.hierarchy,
        'create',
        groupTarget.data,
        false,
        serverNode.url_jump_after_node
      )
      : '/browser/server/obj/1/';
  const urlFor = () => baseUrl;

  const displayLabel = profile.engine_display_name || profile.display_name || engineId;
  const defaultPorts = Array.isArray(nodeData?.localhost_ports)
    ? nodeData.localhost_ports
    : profile.default_port
      ? [profile.default_port]
      : [];
  const initialData = {
    name: gettext('%s on localhost', displayLabel),
    cde_profile_id: profile.profile_id,
    cde_registration_intent: 'endpoint',
    host: 'localhost',
    port: profile.default_port,
    db: '',
    connect_now: false,
  };

  const onSaved = (response) => {
    setTimeout(() => serverNode?.clear_cache?.(groupTarget.item), 0);
    const createdId = response?.node?._id ?? response?.node?.id;
    void refreshConnectorAfterServerSave(
      profile.engine_id,
      groupTarget.item,
      createdId
    ).then((refreshed) => {
      if (!refreshed && response?.node && groupTarget.hierarchy) {
        pgAdmin?.Browser?.Events?.trigger?.(
          'pgadmin:browser:tree:add',
          {...response.node},
          {...groupTarget.hierarchy}
        );
      }
      setFormIteration((n) => n + 1);
    });
    pgAdmin?.Browser?.notifier?.success?.(
      gettext('Server settings applied.')
    );
  };

  return (
    <Box
      data-cdeadmin-qa-key={`localhost-server-properties-${engineId}`}
      sx={{height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column'}}
    >
      <Box
        sx={{
          px: 3,
          py: 1,
          borderBottom: '1px solid',
          borderColor: 'divider',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 1,
          flexWrap: 'wrap',
        }}
      >
        <Box sx={{fontSize: '0.8rem', color: 'text.secondary'}}>
          <strong>{gettext('%s — localhost', displayLabel)}</strong>
          {' · '}
          {nodeData?.localhost_available
            ? gettext('Local listener detected')
            : defaultPorts.length > 0
              ? gettext('Not detected on default port %s', defaultPorts.join(', '))
              : gettext('Not detected on default port')}
        </Box>
        <Button
          size="small"
          intent="neutral"
          data-cdeadmin-qa-key="localhost-open-properties-tab"
          onClick={() =>
            serverNode?.callbacks?.register_engine_server?.call(serverNode, {
              item: nodeItem,
              engineId,
              panelTitle: gettext('Server Properties — %s on localhost', displayLabel),
              applyLabel: gettext('Apply Changes'),
              registrationContext: {
                profile_id: profile.profile_id,
                registration_intent: 'endpoint',
                host: 'localhost',
              },
            })
          }
        >
          {gettext('Open in Separate Tab…')}
        </Button>
      </Box>
      {!nodeData?.localhost_available && (
        <Banner status="info">
          {defaultPorts.length > 0
            ? gettext(
              'localhost is unreachable on default port %s. Update the Server port (for example 53050) and credentials below, then click Apply Changes.',
              defaultPorts.join(', ')
            )
            : gettext(
              'localhost is unreachable on its default port. Update the Server port and credentials below, then click Apply Changes.'
            )}
        </Banner>
      )}
      <Box sx={{flex: 1, minHeight: 0}}>
        <ServerRegistrationHost
          key={`localhost-${profile.profile_id}-${formIteration}`}
          api={api}
          engine={profile.engine_id}
          mode="create"
          urlFor={urlFor}
          initialData={initialData}
          profileId={profile.profile_id}
          intent="endpoint"
          verifyNow="auto"
          applyLabel={gettext('Apply Changes')}
          displayName={gettext('Server Properties — %s on localhost', displayLabel)}
          onSaved={onSaved}
        />
      </Box>
    </Box>
  );
}

LocalhostServerProperties.propTypes = {
  nodeData: PropTypes.object,
  nodeItem: PropTypes.object,
};

function ServerSettingsProperties({node, treeNodeInfo, nodeData, nodeItem}) {
  const pgAdmin = usePgAdmin();
  const api = getApiInstance();
  const serverNode = node || pgAdmin?.Browser?.Nodes?.server;
  const engine = nodeData?.cde_engine_id;
  const [saveCount, setSaveCount] = useState(0);
  const [, setNodeRevision] = useState(0);
  useEffect(() => {
    const events = pgAdmin?.Browser?.Events;
    if (!events?.on) return undefined;
    const bump = () => setNodeRevision((n) => n + 1);
    events.on('pgadmin:browser:node:updated', bump);
    return () => events.off?.('pgadmin:browser:node:updated', bump);
  }, [pgAdmin]);
  const base =
    serverNode && treeNodeInfo
      ? generateNodeUrl.call(
        serverNode,
        treeNodeInfo,
        'edit',
        nodeData,
        false,
        serverNode.url_jump_after_node
      )
      : '/browser/server/obj/1/';
  const urlFor = (isNew) => base + (isNew ? '' : nodeData._id);
  const lifecycleUrl = LIFECYCLE_EDIT_ENGINES.has(engine)
    ? urlFor(false).replace('/obj/', '/cde_workspace/')
    : undefined;

  const onSaved = (response) => {
    const tree = pgAdmin?.Browser?.tree;
    setTimeout(() => serverNode?.clear_cache?.(nodeItem), 0);
    setSaveCount((n) => n + 1);
    if (!response?.node) {
      tree?.refresh?.(nodeItem);
      pgAdmin?.Browser?.notifier?.success?.(gettext('Server settings applied.'));
      return;
    }
    pgAdmin?.Browser?.Events?.trigger?.(
      'pgadmin:browser:tree:update',
      nodeData,
      response.node,
      treeNodeInfo,
      {
        success: (updated, next, previous) => {
          pgAdmin?.Browser?.Events?.trigger?.('pgadmin:browser:node:updated', updated, next, previous);
          pgAdmin?.Browser?.Events?.trigger?.('pgadmin:browser:node:server:updated', updated, next, previous);
          if (nodeData?.cde_endpoint) {
            serverNode?.callbacks?.refresh?.call(serverNode, null, nodeItem);
          }
        },
      }
    );
    if (response.info) {
      pgAdmin?.Browser?.notifier?.warning?.(
        gettext('Server settings applied (%s).', response.info)
      );
    } else {
      pgAdmin?.Browser?.notifier?.success?.(gettext('Server settings applied.'));
    }
  };

  const verification = nodeData?.runtime_verification_state;
  const isVerified = verification === 'verified' || Boolean(nodeData?.connected);
  const serverMenus = providerContextMenuItems(nodeData, nodeItem) || [];
  const createDbMenu = serverMenus.find((m) => String(m.commandId).endsWith('.create_database'));
  const registerDbMenu = serverMenus.find((m) => String(m.commandId).endsWith('.register_database'));
  const invokeProviderMenu = (menu) =>
    menu?.commandHandler?.(
      menu.commandArguments({itemData: nodeData, item: nodeItem}),
      {itemData: nodeData, item: nodeItem}
    );

  return (
    <Box
      data-cdeadmin-qa-key={`server-settings-panel-${nodeData?._id}`}
      sx={{height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column'}}
    >
      <Box
        sx={{
          px: 3,
          py: 0.75,
          borderBottom: '1px solid',
          borderColor: 'divider',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 1,
          flexWrap: 'wrap',
        }}
      >
        <Box sx={{fontSize: '0.8rem', color: 'text.secondary'}}>
          <strong>{nodeData?.label || nodeData?._label}</strong>
          {' · '}
          {isVerified ? gettext('Verified / Ready') : gettext('Not yet verified')}
          {nodeData?.verified_runtime_version ? ` (${nodeData.verified_runtime_version})` : ''}
        </Box>
        <Box sx={{display: 'flex', gap: 0.75, flexWrap: 'wrap'}}>
          <Button
            size="small"
            intent="neutral"
            data-cdeadmin-qa-key="server-settings-verify"
            onClick={() => serverNode?.callbacks?.connect_server?.call(serverNode, {item: nodeItem})}
          >
            {isVerified ? gettext('Re-verify / Connect…') : gettext('Verify / Connect…')}
          </Button>
          {createDbMenu && (
            <Button
              size="small"
              intent="neutral"
              disabled={!canLaunchServerMenu(createDbMenu, nodeData, nodeItem)}
              title={
                canLaunchServerMenu(createDbMenu, nodeData, nodeItem)
                  ? createDbMenu.label
                  : createDbMenu.disabledReason || createDbMenu.label
              }
              data-cdeadmin-qa-key="server-settings-create-database"
              onClick={() => invokeProviderMenu(createDbMenu)}
            >
              {gettext('Create Database…')}
            </Button>
          )}
          {registerDbMenu && (
            <Button
              size="small"
              intent="neutral"
              disabled={!canLaunchServerMenu(registerDbMenu, nodeData, nodeItem)}
              title={
                canLaunchServerMenu(registerDbMenu, nodeData, nodeItem)
                  ? registerDbMenu.label
                  : registerDbMenu.disabledReason || registerDbMenu.label
              }
              data-cdeadmin-qa-key="server-settings-register-database"
              onClick={() => invokeProviderMenu(registerDbMenu)}
            >
              {gettext('Register Database…')}
            </Button>
          )}
          <Button
            size="small"
            intent="neutral"
            data-cdeadmin-qa-key="server-settings-open-tab"
            onClick={() =>
              serverNode?.callbacks?.show_obj_properties?.call(serverNode, {
                action: 'edit',
                item: nodeItem,
              })
            }
          >
            {gettext('Open in Separate Tab…')}
          </Button>
          <Button
            size="small"
            intent="danger"
            data-cdeadmin-qa-key="server-settings-remove"
            onClick={() =>
              serverNode?.callbacks?.delete_obj?.call(serverNode, {
                item: nodeItem,
                url: 'drop',
              })
            }
          >
            {gettext('Remove Server…')}
          </Button>
        </Box>
      </Box>
      <Box sx={{flex: 1, minHeight: 0}}>
        <ServerRegistrationHost
          key={`server-settings-${nodeData?._id}-${saveCount}`}
          api={api}
          engine={engine}
          version={nodeData?.verified_runtime_version}
          versionSupport={nodeData?.version_support}
          mode="alter"
          urlFor={urlFor}
          profileId={nodeData?.cde_profile_id}
          lifecycleUrl={lifecycleUrl}
          verifyNow="auto"
          applyLabel={gettext('Apply Changes')}
          displayName={gettext('Server Properties — %s', nodeData?.label || nodeData?._label)}
          onSaved={onSaved}
        />
      </Box>
    </Box>
  );
}

ServerSettingsProperties.propTypes = {
  node: PropTypes.func,
  treeNodeInfo: PropTypes.object,
  nodeData: PropTypes.object,
  nodeItem: PropTypes.object,
};

function DatabaseTargetProperties({nodeData, nodeItem}) {
  const pgAdmin = usePgAdmin();
  const tree = pgAdmin?.Browser?.tree;
  let parentServerData = null;
  let cur = nodeItem && tree?.hasParent?.(nodeItem) ? tree.parent(nodeItem) : null;
  while (cur && !parentServerData) {
    const d = tree?.itemData?.(cur);
    if (d?._type === 'server') parentServerData = d;
    cur = !parentServerData && tree?.hasParent?.(cur) ? tree.parent(cur) : null;
  }

  const profile = endpointProfiles?.get?.(nodeData?.cde_profile_id);
  const engineLabel =
    profile?.engine_display_name || profile?.display_name || nodeData?.cde_engine_id || '';
  const menus = providerContextMenuItems(nodeData, nodeItem) || [];
  const findAction = (suffix) =>
    menus.find((m) => String(m.commandId).split('.').at(-1) === suffix);

  const connectMenu = findAction('connect');
  const studioMenu = findAction('studio');
  const editMenu = findAction('edit') || findAction('alter') || findAction('properties');
  const removeMenu = findAction('remove');
  const dropMenu = findAction('drop');

  const invokeMenu = (menu) =>
    menu?.commandHandler?.(
      menu.commandArguments({itemData: nodeData, item: nodeItem}),
      {itemData: nodeData, item: nodeItem}
    );

  const rows = [
    [gettext('Database'), nodeData?.label || nodeData?._label || nodeData?.cde_database || '—'],
    [gettext('Target path / alias'), nodeData?.cde_database || nodeData?._id || '—'],
    [gettext('Engine'), engineLabel || '—'],
    [gettext('Server'), parentServerData?.label || parentServerData?._label || '—'],
    [
      gettext('Status'),
      nodeData?.cde_database_active ? gettext('Connected / Active') : gettext('Registered'),
    ],
  ];

  return (
    <Box
      data-cdeadmin-qa-key={`database-target-properties-${nodeData?._id}`}
      sx={{height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column'}}
    >
      <Box
        sx={{
          px: 3,
          py: 0.75,
          borderBottom: '1px solid',
          borderColor: 'divider',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 1,
          flexWrap: 'wrap',
        }}
      >
        <Box sx={{fontSize: '0.8rem', color: 'text.secondary'}}>
          <strong>
            {gettext('Database Properties — %s', nodeData?.label || nodeData?._label || '')}
          </strong>
          {engineLabel ? ` · ${engineLabel}` : ''}
        </Box>
        <Box sx={{display: 'flex', gap: 0.75, flexWrap: 'wrap'}}>
          {connectMenu && connectMenu.enable(nodeData, nodeItem) && (
            <Button
              size="small"
              intent="neutral"
              data-cdeadmin-qa-key="database-target-connect"
              onClick={() => invokeMenu(connectMenu)}
            >
              {gettext('Connect…')}
            </Button>
          )}
          {studioMenu && (
            <Button
              size="small"
              intent="primary"
              disabled={!studioMenu.enable(nodeData, nodeItem)}
              data-cdeadmin-qa-key="database-target-sql"
              onClick={() => invokeMenu(studioMenu)}
            >
              {gettext('Open SQL Editor…')}
            </Button>
          )}
          {editMenu && (
            <Button
              size="small"
              intent="neutral"
              disabled={!editMenu.enable(nodeData, nodeItem)}
              data-cdeadmin-qa-key="database-target-edit"
              onClick={() => invokeMenu(editMenu)}
            >
              {gettext('Edit Connection / Settings…')}
            </Button>
          )}
          {removeMenu && (
            <Button
              size="small"
              intent="danger"
              disabled={!removeMenu.enable(nodeData, nodeItem)}
              title={removeMenu.disabledReason || removeMenu.label}
              data-cdeadmin-qa-key="database-target-remove"
              onClick={() => invokeMenu(removeMenu)}
            >
              {gettext('Remove Database…')}
            </Button>
          )}
          {dropMenu && dropMenu.enable(nodeData, nodeItem) && (
            <Button
              size="small"
              intent="danger"
              data-cdeadmin-qa-key="database-target-drop"
              onClick={() => invokeMenu(dropMenu)}
            >
              {gettext('Drop Database…')}
            </Button>
          )}
        </Box>
      </Box>
      <Box sx={{p: 2, overflowY: 'auto', flex: 1, minHeight: 0}}>
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: 'minmax(140px, 200px) 1fr',
            rowGap: 1,
            columnGap: 2,
            fontSize: '0.8125rem',
            maxWidth: 680,
          }}
        >
          {rows.map(([label, val]) => (
            <Box key={label} sx={{display: 'contents'}}>
              <Box sx={{fontWeight: 600, color: 'text.secondary'}}>{label}</Box>
              <Box sx={{wordBreak: 'break-all'}}>{val}</Box>
            </Box>
          ))}
        </Box>
      </Box>
    </Box>
  );
}

DatabaseTargetProperties.propTypes = {
  nodeData: PropTypes.object,
  nodeItem: PropTypes.object,
};

function Properties(props) {
  const isCollection = props.nodeData?._type?.startsWith('coll-') || props.nodeData?._type == 'dbms_job_scheduler';
  const pgAdmin = usePgAdmin();
  let noPropertyMsg = '';

  if (props.nodeData?._type === 'cde_resource') {
    return <StyledBox><ErrorBoundary>
      <ProviderObjectProperties key={props.nodeData.cde_resource_id}
        nodeData={props.nodeData} />
    </ErrorBoundary></StyledBox>;
  }

  if (props.nodeData?._type === 'cde_database_target') {
    return (
      <StyledBox>
        <ErrorBoundary>
          <DatabaseTargetProperties
            nodeData={props.nodeData}
            nodeItem={props.nodeItem}
          />
        </ErrorBoundary>
      </StyledBox>
    );
  }

  if (props.nodeData?._type === 'localhost_placeholder') {
    return (
      <StyledBox>
        <ErrorBoundary>
          <LocalhostServerProperties
            nodeData={props.nodeData}
            nodeItem={props.nodeItem}
          />
        </ErrorBoundary>
      </StyledBox>
    );
  }

  if (props.nodeData?._type === 'engine_type') {
    return (
      <StyledBox>
        <ErrorBoundary>
          <ConnectorRegistrationProperties
            nodeData={props.nodeData}
            nodeItem={props.nodeItem}
          />
        </ErrorBoundary>
      </StyledBox>
    );
  }

  if (
    props.nodeData?._type === 'server' &&
    props.nodeData?.cde_engine_id &&
    LEGACY_REGISTRATION_RETIRED.has(props.nodeData.cde_engine_id)
  ) {
    return (
      <StyledBox>
        <ErrorBoundary>
          <ServerSettingsProperties
            node={props.node}
            treeNodeInfo={props.treeNodeInfo}
            nodeData={props.nodeData}
            nodeItem={props.nodeItem}
          />
        </ErrorBoundary>
      </StyledBox>
    );
  }

  if (!props.node) {
    noPropertyMsg = gettext('Please select an object in the tree view.');
  } else if (!_.isUndefined(props.node.hasProperties) && !props.node.hasProperties) {
    noPropertyMsg = gettext('No information is available for the selected object.');
  }

  if(noPropertyMsg) {
    return (
      <StyledBox>
        <Box sx={{my: '4px', width: '100%', minWidth: 0}}>
          <EmptyPanelMessage text={noPropertyMsg} />
        </Box>
      </StyledBox>
    );
  }

  if(isCollection) {
    return (
      <StyledBox>
        <ErrorBoundary>
          <CollectionNodeProperties
            {...props}
          />
        </ErrorBoundary>
      </StyledBox>
    );
  } else {
    return (
      <StyledBox>
        <ErrorBoundary>
          <ObjectNodeProperties
            {...props}
            actionType='properties'
            formType="tab"
            onEdit={()=>{
              pgAdmin.Browser.Node.callbacks.show_obj_properties.call(
                props.node, {action: 'edit'}
              );
            }}
          />
        </ErrorBoundary>
      </StyledBox>
    );
  }
}

Properties.propTypes = {
  node: PropTypes.func,
  treeNodeInfo: PropTypes.object,
  nodeData: PropTypes.object,
  nodeItem: PropTypes.object,
};

export default withStandardTabInfo(Properties, BROWSER_PANELS.PROPERTIES);
