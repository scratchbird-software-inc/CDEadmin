/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * The grants view for one object. Chooses by the engine's security.json
 * status (design Decision 21), never by engine name: a complete descriptor
 * that offers grants on this kind of object is served by the descriptor-driven
 * view, anything else by the previous permissions matrix.
 */

import {useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import getApiInstance from 'sources/api_instance';
import {descriptorClient} from '../objects/DescriptorClient';
import DescriptorObjectGrants, {objectGrantsOffered} from './DescriptorObjectGrants';
import ObjectPermissionsMatrix from './ObjectPermissionsMatrix';

/** What the tree node says about where and what the object is. */
export function objectContext(boundNodeData, resource) {
  const node = boundNodeData || {};
  return {
    engine: String(node.cde_engine_id || node.engine_id || '').toLowerCase(),
    endpointUrl: node.cde_workspace_url,
    databaseTargetId: node.cde_database_target_id || '',
    version: node.verified_runtime_version,
    objectKind: String(node.cde_resource_kind || resource?.resource_kind || '').toLowerCase(),
    objectName: resource?.display_name || node.label || '',
    objectPath: Array.isArray(resource?.display_path) ? resource.display_path.map(String) : undefined,
  };
}

export default function ObjectGrantsSurface(props) {
  const {boundNodeData, resource, api: apiProp} = props;
  const context = objectContext(boundNodeData, resource);
  const ready = Boolean(context.engine && context.endpointUrl && context.objectKind && context.objectName);
  const [choice, setChoice] = useState(ready ? 'checking' : 'legacy');
  const [api] = useState(() => apiProp || (ready ? getApiInstance() : null));

  useEffect(() => {
    if(!ready || !api) { setChoice('legacy'); return undefined; }
    let cancelled = false;
    descriptorClient(api).bundle(context.engine, {version: context.version})
      .then((bundle) => { if(!cancelled) setChoice(objectGrantsOffered(bundle, context.objectKind) ? 'descriptor' : 'legacy'); })
      .catch(() => { if(!cancelled) setChoice('legacy'); });
    return () => { cancelled = true; };
  }, [api, ready, context.engine, context.version, context.objectKind]);

  if(choice === 'checking') return null;
  if(choice === 'descriptor') {
    return <DescriptorObjectGrants api={api} endpointUrl={context.endpointUrl} engine={context.engine}
      version={context.version} databaseTargetId={context.databaseTargetId}
      objectKind={context.objectKind} objectName={context.objectName} objectPath={context.objectPath} onApplied={props.onApplied} />;
  }
  return <ObjectPermissionsMatrix {...props} />;
}

ObjectGrantsSurface.propTypes = {
  boundNodeData: PropTypes.object,
  resource: PropTypes.object,
  api: PropTypes.object,
  onApplied: PropTypes.func,
};
