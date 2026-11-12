/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// Compact paging chrome. The owner supplies native/cached navigation semantics.
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box} from '../primitives/Layout';
import {IconButton} from '../primitives/Button';
import {Tooltip} from '../navigation/AdvancedNavigation';

export function GridAction({label, children, disabled = false, onClick, ...props}) {
  return (
    <Tooltip title={label}>
      <span style={{display: 'inline-flex'}}>
        <IconButton label={label} disabled={disabled} onClick={onClick} {...props}>
          {children}
        </IconButton>
      </span>
    </Tooltip>
  );
}

GridAction.propTypes = {
  label: PropTypes.string.isRequired,
  children: PropTypes.node,
  disabled: PropTypes.bool,
  onClick: PropTypes.func,
};

export default function GridNavigation({
  page,
  pages,
  busy = false,
  canNext = false,
  endKnown = false,
  onFirst,
  onPrevious,
  onNext,
  onLast,
  nextLabel,
  children,
}) {
  return (
    <Box
      role="group"
      aria-label={gettext('Row navigation')}
      className="sr-bui-toolbar"
      sx={{display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 0.75, py: 0.5}}
    >
      <GridAction label={gettext('First page')} disabled={busy || page <= 0} onClick={onFirst}>
        {'|<'}
      </GridAction>
      <GridAction label={gettext('Previous page')} disabled={busy || page <= 0} onClick={onPrevious}>
        {'<<'}
      </GridAction>
      <Box component="span" role="status" sx={{px: 1, fontSize: '0.78rem', fontWeight: 600}}>
        {endKnown
          ? gettext('Page %s of %s', pages ? page + 1 : 0, pages)
          : gettext('Page %s (end not yet known)', pages ? page + 1 : 0)}
      </Box>
      <GridAction
        label={nextLabel || gettext('Next page')}
        disabled={busy || !canNext}
        onClick={onNext}
      >
        {'>>'}
      </GridAction>
      <GridAction
        label={endKnown ? gettext('Last page') : gettext('Last page (end not yet known)')}
        disabled={busy || !endKnown || page >= pages - 1}
        onClick={onLast}
      >
        {'>|'}
      </GridAction>
      {children}
    </Box>
  );
}

GridNavigation.propTypes = {
  page: PropTypes.number.isRequired,
  pages: PropTypes.number.isRequired,
  nextLabel: PropTypes.string,
  busy: PropTypes.bool,
  canNext: PropTypes.bool,
  endKnown: PropTypes.bool,
  onFirst: PropTypes.func,
  onPrevious: PropTypes.func,
  onNext: PropTypes.func,
  onLast: PropTypes.func,
  children: PropTypes.node,
};
