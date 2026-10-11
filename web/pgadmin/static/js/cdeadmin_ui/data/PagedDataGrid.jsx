import {useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import {Box, MenuItem, TextField} from '@mui/material';
import gettext from 'sources/gettext';
import DataGrid from './DataGrid';
import GridNavigation from './GridNavigation';

// Finite, already-retrieved results only. Native cursors retain their own owner.
export default function PagedDataGrid({rows=[], readOnly=false, pagination=readOnly, ...props}) {
  const [page, setPage] = useState(0), [size, setSize] = useState(100);
  useEffect(() => {setPage(0);}, [props.gridId]);
  if (!pagination) return <DataGrid rows={rows} readOnly={readOnly} {...props} />;
  const count = Math.ceil(rows.length / size), current = Math.min(page, Math.max(0, count - 1));
  return <Box sx={{display: 'flex', flexDirection: 'column', flex: 1,
    height: '100%', minHeight: 180, minWidth: 0, overflow: 'auto'}}>
    <GridNavigation page={current} pages={count} endKnown canNext={current < count - 1}
      onFirst={() => setPage(0)} onPrevious={() => setPage(current - 1)}
      onNext={() => setPage(current + 1)} onLast={() => setPage(count - 1)}>
      <TextField select size="small" label={gettext('Rows per page')} value={size}
        onChange={(event) => {setSize(Number(event.target.value)); setPage(0);}}>
        {[25, 50, 100, 200, 500].map(value => <MenuItem key={value} value={value}>{value}</MenuItem>)}
      </TextField>
      <span>{gettext('%s rows in this result', rows.length)}</span>
    </GridNavigation>
    <Box sx={{flex: 1, minHeight: 120, minWidth: 0, overflow: 'auto'}}>
      <DataGrid key={current} rows={rows.slice(current * size, (current + 1) * size)}
        readOnly={readOnly} {...props} />
    </Box>
  </Box>;
}
PagedDataGrid.propTypes = {rows: PropTypes.array, readOnly: PropTypes.bool,
  pagination: PropTypes.bool, gridId: PropTypes.string};
