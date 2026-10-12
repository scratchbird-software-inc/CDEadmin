// Compact paging chrome. The owner supplies native/cached navigation semantics.
import PropTypes from 'prop-types';
import {Box, IconButton, Tooltip} from '@mui/material';
import gettext from 'sources/gettext';

export function GridAction({label, children, ...props}) {
  return <Tooltip title={label}><span style={{display: 'inline-flex'}}>
    <IconButton size="small" aria-label={label} {...props}>{children}</IconButton>
  </span></Tooltip>;
}
GridAction.propTypes = {label: PropTypes.string.isRequired, children: PropTypes.node};

export default function GridNavigation({page, pages, busy=false, canNext=false,
  endKnown=false, onFirst, onPrevious, onNext, onLast, nextLabel, children}) {
  return <Box role="group" aria-label={gettext('Row navigation')}
    sx={{display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 0.5, py: 0.5}}>
    <GridAction label={gettext('First page')} disabled={busy || page <= 0} onClick={onFirst}>{'|<'}</GridAction>
    <GridAction label={gettext('Previous page')} disabled={busy || page <= 0} onClick={onPrevious}>{'<<'}</GridAction>
    <Box component="span" role="status" sx={{px: 1}}>
      {endKnown ? gettext('Page %s of %s', pages ? page + 1 : 0, pages) :
        gettext('Page %s (end not yet known)', pages ? page + 1 : 0)}
    </Box>
    <GridAction label={nextLabel || gettext('Next page')} disabled={busy || !canNext} onClick={onNext}>{'>>'}</GridAction>
    <GridAction label={endKnown ? gettext('Last page') : gettext('Last page (end not yet known)')}
      disabled={busy || !endKnown || page >= pages - 1} onClick={onLast}>{'>|'}</GridAction>
    {children}
  </Box>;
}
GridNavigation.propTypes = {page: PropTypes.number.isRequired, pages: PropTypes.number.isRequired,
  nextLabel: PropTypes.string, busy: PropTypes.bool, canNext: PropTypes.bool, endKnown: PropTypes.bool,
  onFirst: PropTypes.func, onPrevious: PropTypes.func, onNext: PropTypes.func,
  onLast: PropTypes.func, children: PropTypes.node};
