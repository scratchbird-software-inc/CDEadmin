/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {Suspense, lazy} from 'react';

/**
 * Wrap a dynamic import() component in React.lazy + Suspense so forms,
 * dialogs, and engine workspaces are loaded on demand by the client
 * while keeping database state and compilation on the Python host.
 */
export function lazySurface(loader, displayName = 'LazySurface') {
  const LazyComponent = lazy(loader);
  function OnDemandSurface(props) {
    return (
      <Suspense
        fallback={
          <div
            className="sr-lazy-surface-loading"
            data-testid="sr-lazy-surface-loading"
            aria-busy="true"
          />
        }
      >
        <LazyComponent {...props} />
      </Suspense>
    );
  }
  OnDemandSurface.displayName = displayName;
  return OnDemandSurface;
}

export default lazySurface;
