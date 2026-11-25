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
import ObjectNodeProperties from './ObjectNodeProperties';
import EmptyPanelMessage from '../../static/js/components/EmptyPanelMessage';
import getApiInstance from 'sources/api_instance';
import gettext from 'sources/gettext';
import endpointProfiles from 'pgadmin.cdeadmin.endpoint_profiles';
import {
  Banner,
  Icon,
  semanticObjectIconKey,
  useProjectInstanceScope,
  useProjectShell,
} from 'sources/cdeadmin_ui';
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

function useLanguageRevision() {
  const [rev, setRev] = useState(0);
  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const bump = () => setRev((n) => n + 1);
    window.addEventListener('scratchrobin:language-changed', bump);
    return () => window.removeEventListener('scratchrobin:language-changed', bump);
  }, []);
  return rev;
}

export function resolveConnectorModeSelection(engineId, requestedProfileId, requestedIntent) {
  const normalizedEngine = engineId === 'opensearch_sql_ppl' ? 'opensearch' : engineId;
  const profiles = endpointProfiles?.interfaces?.(normalizedEngine) || [];
  if (!profiles.length) {
    return {
      profiles: [],
      profile: null,
      activeIntent: 'endpoint',
      networkSupportsDatabaseIntent: false,
      networkSupportsCreateIntent: false,
    };
  }
  const profile =
    profiles.find((p) => p.profile_id === requestedProfileId) || profiles[0];
  const networkSupportsDatabaseIntent = Boolean(
    profile.route_kind !== 'embedded_file' && profile.database_targeting?.multiple
  );
  const networkSupportsCreateIntent = Boolean(
    networkSupportsDatabaseIntent && profile.database_targeting?.create_and_activate
  );
  const intent = requestedIntent || 'endpoint';
  const activeIntent =
    profile.route_kind === 'embedded_file' && intent === 'endpoint'
      ? 'register_existing'
      : profile.route_kind !== 'embedded_file' && !networkSupportsDatabaseIntent && intent !== 'endpoint'
        ? 'endpoint'
        : profile.route_kind !== 'embedded_file' && intent === 'create_database' && !networkSupportsCreateIntent
          ? 'endpoint'
          : intent;
  return {
    profiles,
    profile,
    activeIntent,
    networkSupportsDatabaseIntent,
    networkSupportsCreateIntent,
  };
}

function ConnectorRegistrationProperties({nodeData, nodeItem}) {
  const pgAdmin = usePgAdmin();
  useLanguageRevision();
  const shell = useProjectShell();
  const instanceScope = useProjectInstanceScope();
  const enclosingInstance =
    instanceScope && shell?.instances
      ? shell.instances.find((inst) => inst.instanceId === instanceScope.instanceId)
      : null;

  const rawEngineId = nodeData?.engine_id || nodeData?._id || '';
  const engineId = rawEngineId === 'opensearch_sql_ppl' ? 'opensearch' : rawEngineId;
  const [fallbackProfileId, setFallbackProfileId] = useState(null);
  const [fallbackIntent, setFallbackIntent] = useState('endpoint');
  const [formIteration, setFormIteration] = useState(0);

  const selectedProfileId = enclosingInstance
    ? enclosingInstance.meta?.connectorProfileId ?? null
    : fallbackProfileId;
  const intent = enclosingInstance
    ? enclosingInstance.meta?.connectorIntent || 'endpoint'
    : fallbackIntent;

  useEffect(() => {
    if (enclosingInstance || typeof window === 'undefined') return undefined;
    const onModeEvent = (ev) => {
      if (ev?.detail?.profileId !== undefined) setFallbackProfileId(ev.detail.profileId);
      if (ev?.detail?.intent !== undefined) setFallbackIntent(ev.detail.intent);
    };
    window.addEventListener('scratchrobin:connector-select-mode', onModeEvent);
    return () => window.removeEventListener('scratchrobin:connector-select-mode', onModeEvent);
  }, [enclosingInstance]);

  const {profiles, profile, activeIntent} = resolveConnectorModeSelection(
    engineId,
    selectedProfileId,
    intent
  );

  if (!profiles.length || !profile) {
    return (
      <Box sx={{my: '4px', width: '100%', minWidth: 0}}>
        <EmptyPanelMessage text={gettext('No registration profile is available for this connector.')} />
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
  useLanguageRevision();
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
        <Box sx={{fontSize: '0.85rem', color: 'text.secondary'}}>
          <strong style={{color: 'inherit'}}>
            {gettext('Database Properties — %s', nodeData?.label || nodeData?._label || '')}
          </strong>
          {engineLabel ? ` · ${engineLabel}` : ''}
        </Box>
      </Box>
      <Box sx={{p: 2.5, overflowY: 'auto', flex: 1, minHeight: 0}}>
        <Box
          data-cdeadmin-qa-key="auto-placing-properties-grid"
          sx={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
            rowGap: 1.5,
            columnGap: 2,
            alignItems: 'start',
          }}
        >
          {rows.map(([label, val]) => (
            <Box
              key={label}
              sx={{
                display: 'flex',
                flexDirection: 'column',
                gap: 0.4,
                minWidth: 0,
              }}
            >
              <Box sx={{fontSize: '0.75rem', fontWeight: 600, color: 'text.secondary', lineHeight: 1.25}}>
                {label}
              </Box>
              <Box
                sx={{
                  px: 1.25,
                  py: 0.65,
                  borderRadius: 1,
                  border: '1px solid',
                  borderColor: 'divider',
                  bgcolor: 'background.paper',
                  fontSize: '0.8125rem',
                  minHeight: '2rem',
                  display: 'flex',
                  alignItems: 'center',
                  overflowWrap: 'anywhere',
                }}
              >
                {val}
              </Box>
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

function VirtualTreeGroupItemsView({nodeData, nodeItem}) {
  const pgAdmin = usePgAdmin();
  useLanguageRevision();
  const [treeRev, setTreeRev] = useState(0);
  const [loadingChildren, setLoadingChildren] = useState(false);

  const tree = pgAdmin?.Browser?.tree;
  const resolvedItem = nodeItem || tree?.selected?.() || null;

  useEffect(() => {
    const events = pgAdmin?.Browser?.Events;
    if (!events?.on) return undefined;
    const bump = () => setTreeRev((n) => n + 1);
    events.on('pgadmin-browser:tree:updated', bump);
    events.on('pgadmin:browser:node:updated', bump);
    events.on('pgadmin:browser:tree:add', bump);
    return () => {
      events.off?.('pgadmin-browser:tree:updated', bump);
      events.off?.('pgadmin:browser:node:updated', bump);
      events.off?.('pgadmin:browser:tree:add', bump);
    };
  }, [pgAdmin]);

  useEffect(() => {
    if (!tree || !resolvedItem) return undefined;
    const existingChildren = tree.children?.(resolvedItem) || resolvedItem.children || [];
    const canExpand = Boolean(nodeData?.inode || resolvedItem.type === 1 || typeof resolvedItem.ensureLoaded === 'function');
    if (existingChildren.length > 0 || !canExpand) return undefined;

    let active = true;
    setLoadingChildren(true);
    const loadPromise =
      typeof tree.open === 'function'
        ? Promise.resolve(tree.open(resolvedItem))
        : typeof resolvedItem.ensureLoaded === 'function'
          ? Promise.resolve(resolvedItem.ensureLoaded())
          : Promise.resolve();
    loadPromise
      .catch(() => {})
      .finally(() => {
        if (active) {
          setLoadingChildren(false);
          setTreeRev((n) => n + 1);
        }
      });
    return () => {
      active = false;
    };
  }, [nodeData?.inode, resolvedItem, tree]);

  // Reference treeRev so React lint / render tracks updates
  void treeRev;
  const childItems =
    (resolvedItem && (tree?.children?.(resolvedItem) || resolvedItem.children)) || [];

  const rawGroupTitle = String(nodeData?.label || nodeData?._label || '')
    .replace(/\s*\(\d+\)\s*$/, '')
    .trim();
  const groupTitle = rawGroupTitle ? gettext(rawGroupTitle) : gettext('Items');

  const handleSelectChild = (child) => {
    if (!tree || !child) return;
    const childData = tree.itemData?.(child) || child._metadata?.data || {};
    void Promise.resolve(tree.select?.(child, true, 'center')).then(() => {
      pgAdmin?.Browser?.Events?.trigger?.('pgadmin-browser:tree:selected', child, childData);
    });
  };

  return (
    <Box
      data-cdeadmin-qa-key={`virtual-group-items-${rawGroupTitle || nodeData?._type || 'group'}`}
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
        <Box sx={{fontSize: '0.85rem', color: 'text.secondary'}}>
          <strong style={{color: 'inherit'}}>{groupTitle}</strong>
          {' · '}
          {gettext('%s items', String(childItems.length))}
        </Box>
      </Box>
      <Box sx={{p: 2.5, overflowY: 'auto', flex: 1, minHeight: 0}}>
        {loadingChildren && childItems.length === 0 ? (
          <EmptyPanelMessage text={gettext('Loading items…')} />
        ) : childItems.length === 0 ? (
          <EmptyPanelMessage text={gettext('No items in this group.')} />
        ) : (
          <Box
            data-cdeadmin-qa-key="virtual-group-buttons-grid"
            sx={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
              gap: 1.25,
              alignItems: 'stretch',
            }}
          >
            {childItems.map((child, idx) => {
              const cData = tree?.itemData?.(child) || child?._metadata?.data || {};
              const rawChildLabel = String(
                cData.label || cData._label || child?.fileName || `Item ${idx + 1}`
              ).trim();
              const cleanLabel = cData.inode
                ? gettext(rawChildLabel.replace(/\s*\(\d+\)\s*$/, '').trim() || rawChildLabel)
                : rawChildLabel;
              const iconKey =
                (typeof cData.icon === 'string' && cData.icon.trim()) ||
                semanticObjectIconKey(cData.cde_resource_kind || cData._type || 'table');
              const childKey =
                cData.cde_resource_id ||
                cData._id ||
                cData.id ||
                child?.path ||
                `${rawChildLabel}-${idx}`;
              return (
                <Box
                  key={String(childKey)}
                  component="button"
                  type="button"
                  title={cleanLabel}
                  data-cdeadmin-qa-key={`virtual-group-item-btn-${rawChildLabel}`}
                  onClick={() => handleSelectChild(child)}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1.1,
                    px: 1.5,
                    py: 1,
                    borderRadius: 1.25,
                    border: '1px solid',
                    borderColor: 'divider',
                    bgcolor: 'background.paper',
                    color: 'text.primary',
                    fontSize: '0.8125rem',
                    fontWeight: 600,
                    textAlign: 'left',
                    cursor: 'pointer',
                    minWidth: 0,
                    transition: 'border-color 120ms ease, background-color 120ms ease',
                    '&:hover': {
                      borderColor: 'primary.main',
                      bgcolor: 'action.hover',
                    },
                    '&:focus-visible': {
                      outline: '2px solid',
                      outlineColor: 'primary.main',
                      outlineOffset: '1px',
                    },
                  }}
                >
                  <Box
                    component="span"
                    sx={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      width: 18,
                      height: 18,
                    }}
                  >
                    <Icon iconKey={iconKey} decorative size="1rem" />
                  </Box>
                  <Box
                    component="span"
                    sx={{
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      minWidth: 0,
                      flex: 1,
                    }}
                  >
                    {cleanLabel}
                  </Box>
                </Box>
              );
            })}
          </Box>
        )}
      </Box>
    </Box>
  );
}

VirtualTreeGroupItemsView.propTypes = {
  nodeData: PropTypes.object,
  nodeItem: PropTypes.object,
};

function Properties(props) {
  const isCollection = props.nodeData?._type?.startsWith('coll-') || props.nodeData?._type == 'dbms_job_scheduler';
  const pgAdmin = usePgAdmin();
  let noPropertyMsg = '';

  if (
    props.nodeData?._type === 'cde_resource' ||
    (props.nodeData?.cde_resource_id && props.nodeData?.cde_section)
  ) {
    return <StyledBox><ErrorBoundary>
      <ProviderObjectProperties
        key={`${props.nodeData.cde_resource_id}:${props.nodeData.cde_section || ''}`}
        nodeData={props.nodeData}
      />
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

  if (
    props.nodeData?._type === 'cde_resource_group' ||
    (Boolean(props.nodeData?.inode) &&
      !isCollection &&
      props.node &&
      props.node.hasProperties === false)
  ) {
    return (
      <StyledBox>
        <ErrorBoundary>
          <VirtualTreeGroupItemsView
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
