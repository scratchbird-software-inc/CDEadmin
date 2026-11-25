/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Chooses the Security Manager for an engine by its security.json status
 * (design Decision 21), never by engine name: a `complete` descriptor is served
 * by the descriptor-driven manager, anything else stays on the previous one
 * until that engine's provider operations are verified.
 */

import {useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import {descriptorClient} from '../objects/DescriptorClient';
import DescriptorSecurityManager from './DescriptorSecurityManager';
import PrincipalSecurityManager from './PrincipalSecurityManager';

export default function SecurityManagerSurface(props) {
  const {api, endpointUrl, engine, version} = props;
  const [status, setStatus] = useState(api && endpointUrl ? 'checking' : 'legacy');

  useEffect(() => {
    if(!api || !endpointUrl) return undefined;
    let cancelled = false;
    descriptorClient(api).bundle(engine, {version})
      .then((bundle) => { if(!cancelled) setStatus(bundle?.security?.status === 'complete' ? 'descriptor' : 'legacy'); })
      .catch(() => { if(!cancelled) setStatus('legacy'); });
    return () => { cancelled = true; };
  }, [api, endpointUrl, engine, version]);

  if(status === 'checking') return null;
  if(status === 'descriptor') {
    return <DescriptorSecurityManager api={api} endpointUrl={endpointUrl} engine={engine} version={version}
      scope={props.scope} databaseTargetId={props.databaseTargetId} initialKind={props.initialKind}
      initialPrincipalId={props.initialPrincipalId} endpointLabel={props.endpointLabel} />;
  }
  return <PrincipalSecurityManager {...props} />;
}

SecurityManagerSurface.propTypes = {
  api: PropTypes.object,
  endpointUrl: PropTypes.string,
  engine: PropTypes.string.isRequired,
  version: PropTypes.string,
  scope: PropTypes.string,
  databaseTargetId: PropTypes.string,
  initialKind: PropTypes.string,
  initialPrincipalId: PropTypes.string,
  endpointLabel: PropTypes.string,
};
