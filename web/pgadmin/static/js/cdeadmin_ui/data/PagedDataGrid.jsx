/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box} from '../primitives/Layout';
import {Select} from '../primitives/Choice';
import {ScratchScrollArea} from '../base/ScratchScrollArea';
import {ensureScratchBaseStyles} from '../base/ScratchBaseStyles';
import DataGrid from './DataGrid';
import GridNavigation from './GridNavigation';

const PAGE_SIZE_OPTIONS = [25, 50, 100, 200, 500].map((val) => ({
  value: String(val),
  label: String(val),
}));

// Finite, already-retrieved results only. Native cursors retain their own owner.
export default function PagedDataGrid({rows = [], readOnly = false, pagination = readOnly, ...props}) {
  const [page, setPage] = useState(0);
  const [size, setSize] = useState(100);
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);
  useEffect(() => {
    setPage(0);
  }, [props.gridId]);

  if (!pagination) return <DataGrid rows={rows} readOnly={readOnly} {...props} />;
  const count = Math.ceil(rows.length / size);
  const current = Math.min(page, Math.max(0, count - 1));

  return (
    <Box
      className="sr-bui-table-card"
      sx={{
        display: 'flex',
        flexDirection: 'column',
        flex: 1,
        height: '100%',
        minHeight: 180,
        minWidth: 0,
      }}
    >
      <GridNavigation
        page={current}
        pages={count}
        endKnown
        canNext={current < count - 1}
        onFirst={() => setPage(0)}
        onPrevious={() => setPage(current - 1)}
        onNext={() => setPage(current + 1)}
        onLast={() => setPage(count - 1)}
      >
        <Select
          size="small"
          label={gettext('Rows per page')}
          value={String(size)}
          options={PAGE_SIZE_OPTIONS}
          onChange={(nextVal) => {
            setSize(Number(nextVal) || 100);
            setPage(0);
          }}
          style={{minWidth: 110}}
        />
        <span style={{fontSize: '0.76rem', color: 'var(--sr-text-secondary)'}}>
          {gettext('%s rows in this result', rows.length)}
        </span>
      </GridNavigation>
      <ScratchScrollArea orientation="both" style={{flex: 1, minHeight: 120, minWidth: 0}}>
        <DataGrid
          key={current}
          rows={rows.slice(current * size, (current + 1) * size)}
          readOnly={readOnly}
          {...props}
        />
      </ScratchScrollArea>
    </Box>
  );
}

PagedDataGrid.propTypes = {
  rows: PropTypes.array,
  readOnly: PropTypes.bool,
  pagination: PropTypes.bool,
  gridId: PropTypes.string,
};
