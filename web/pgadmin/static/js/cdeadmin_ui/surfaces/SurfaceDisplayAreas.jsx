/////////////////////////////////////////////////////////////
// Shared display areas for Data Navigator surfaces.
// This software is released under the PostgreSQL Licence.
/////////////////////////////////////////////////////////////

import PropTypes from 'prop-types';

export default function SurfaceDisplayAreas({first, second, ratio, onActivate, qaKey = 'sql-surface-split-view'}) {
  return (
    <div data-cdeadmin-qa-key={qaKey} style={{
      flex: 1, minHeight: 0, minWidth: 0, display: 'flex',
      flexDirection: 'column',
    }}>
      <div data-surface-area="upper" onFocusCapture={onActivate} onPointerDownCapture={onActivate} style={{
        flex: `0 0 ${ratio}%`, minHeight: 100, minWidth: 0, width: '100%', overflow: 'hidden', display: 'flex',
        borderBottom: '2px solid var(--sr-border-default, #cbd5e1)',
      }}>{first}</div>
      <div data-surface-area="lower" onFocusCapture={onActivate} onPointerDownCapture={onActivate}
        style={{flex: 1, minHeight: 100, minWidth: 0, width: '100%', overflow: 'hidden', display: 'flex'}}>{second}</div>
    </div>
  );
}

SurfaceDisplayAreas.propTypes = {
  first: PropTypes.node.isRequired,
  second: PropTypes.node.isRequired,
  qaKey: PropTypes.string,
  onActivate: PropTypes.func,
  ratio: PropTypes.number.isRequired,
};
