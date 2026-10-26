import {useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import getApiInstance from 'sources/api_instance';
import EmptyPanelMessage from 'sources/components/EmptyPanelMessage';
import {descriptorClient} from 'sources/cdeadmin_ui/objects/DescriptorClient';
import FirebirdMonitoring from 'sources/Dialogs/FirebirdMonitoring';
import MySQLMonitoring from 'sources/Dialogs/MySQLMonitoring';

// Viewer implementations are registered once; engine descriptors choose one.
const viewers = {firebird_monitoring: FirebirdMonitoring, relational_monitoring: MySQLMonitoring};

export default function ProviderDashboard({engine, version, serverId, targetId}) {
  const [resolved, setResolved] = useState(null);
  const [error, setError] = useState(null);
  const identity = `${engine}:${version || ''}`;
  useEffect(() => {
    let active = true;
    setError(null);
    descriptorClient(getApiInstance()).bundle(engine, {version}).then(bundle => {
      if(active) setResolved({identity, bundle});
    }).catch(err => {
      if(active) setError({identity, message: err.response?.data?.errormsg || err.message || gettext('Dashboard is unavailable.')});
    });
    return () => { active = false; };
  }, [engine, version]);

  if(error?.identity === identity) return <EmptyPanelMessage text={error.message} />;
  if(resolved?.identity !== identity) return <EmptyPanelMessage text={gettext('Loading dashboard…')} />;
  const scope = targetId ? 'database' : 'endpoint';
  const tool = resolved.bundle.tools?.find(row => row.scope === scope && row.arguments?.dashboard_viewer);
  const Viewer = viewers[tool?.arguments.dashboard_viewer];
  if(!Viewer) return <EmptyPanelMessage text={gettext('No dashboard is configured for this connection.')} />;
  // Monitoring APIs authorize the viewer independently of SQL-session readiness.
  // Never start collection, edit policy or enable inherited PostgreSQL polling.
  return <Viewer key={`${engine}:${serverId}:${targetId || ''}`} engine={engine}
    serverId={Number(serverId)} targetId={targetId} policyMode={false} engineMode={false} />;
}

ProviderDashboard.propTypes = {
  engine: PropTypes.string.isRequired, version: PropTypes.string,
  serverId: PropTypes.oneOfType([PropTypes.number, PropTypes.string]).isRequired,
  targetId: PropTypes.string,
};
