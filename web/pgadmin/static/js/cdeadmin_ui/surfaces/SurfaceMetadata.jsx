import {useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {ScratchScrollArea} from '../base/ScratchScrollArea';

export default function SurfaceMetadata({post, databaseTargetId, resource}) {
  const resourceId = resource?.resource_id;
  const [result, setResult] = useState(null);
  useEffect(() => {
    if (!resourceId) return undefined;
    let active = true;
    Promise.resolve().then(() => post({
      action: 'resource_inspect',
      request: {resource_id: resourceId, database_target_id: databaseTargetId},
    })).then((value) => {
      if (active) setResult({resourceId, value: value?.resource || value});
    }).catch((error) => {
      if (active) setResult({resourceId, error: error?.message || String(error)});
    });
    return () => { active = false; };
  }, [databaseTargetId, post, resourceId]);

  const display = result?.resourceId === resourceId ? result : null;
  const detail = display?.value || {};
  const extension = Object.values(detail.extensions || {}).find((item) => item?.native);
  const native = detail.native || detail.properties || extension?.native || {};
  const sections = [
    ['ddl', gettext('Create Statement'), native.ddl ?? detail.ddl],
    ['comment', gettext('Object Comment'), native.comment ?? native.description ?? detail.comment ?? detail.description],
    ['dependents', gettext('Objects Depending on This Object'), native.dependents ?? detail.dependents],
    ['dependencies', gettext('Objects This Object Depends On'), native.dependencies ?? detail.dependencies],
  ];
  return (
    <ScratchScrollArea orientation="both" fillViewport style={{flex: 1, minHeight: 0}}>
      <div style={{padding: 12}}>
        {!resourceId ? <p>{gettext('Choose an object to inspect its metadata.')}</p> :
          !display ? <p role="status">{gettext('Loading metadata…')}</p> :
            display.error ? <p role="alert">{display.error}</p> :
              sections.map(([key, label, value]) => (
                <section key={key}>
                  <h3>{label}</h3>
                  <pre style={{whiteSpace: 'pre-wrap'}}>{value == null
                    ? gettext('Unavailable')
                    : typeof value === 'string' ? value : JSON.stringify(value, null, 2)}</pre>
                </section>
              ))}
      </div>
    </ScratchScrollArea>
  );
}

SurfaceMetadata.propTypes = {
  post: PropTypes.func.isRequired,
  databaseTargetId: PropTypes.string,
  resource: PropTypes.object,
};
