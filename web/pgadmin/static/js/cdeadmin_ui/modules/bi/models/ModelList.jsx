/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../../../primitives/Layout';
import {Button} from '../../../primitives/Button';
import {EmptyState} from '../../../feedback/EmptyState';
import {Skeleton} from '../../../feedback/Indicators';
import {StatusBadge} from './InsightPanels';

/** Every semantic model on the endpoint; choosing one opens it, "New model" starts an empty draft. */
export default function ModelList({items, status, selectedId, onOpen, onNew, disabled}) {
  return <Stack gap="compact" component="nav" aria-label={gettext('Semantic models')}
    data-cdeadmin-qa-key="bi.models.list" sx={{p: 1, minWidth: 220}}>
    <Button intent="primary" disabled={disabled} onClick={onNew}>{gettext('New model')}</Button>
    {status === 'loading' && <Skeleton lines={3} label={gettext('Loading models')} />}
    {status === 'ready' && !items.length && <EmptyState message={gettext('No semantic models yet.')} />}
    <Box component="ul" sx={{m: 0, p: 0, listStyle: 'none'}}>
      {items.map((item) => <Box component="li" key={item.model_id}>
        <Box component="button" type="button" disabled={disabled} aria-current={item.model_id === selectedId || undefined}
          onClick={() => onOpen(item.model_id)}
          sx={{display: 'flex', width: '100%', gap: 1, alignItems: 'center', textAlign: 'left', cursor: 'pointer',
            p: 0.75, border: 0, borderBottom: '1px solid', borderColor: 'divider', font: 'inherit',
            color: 'text.primary', bgcolor: item.model_id === selectedId ? 'action.selected' : 'transparent'}}>
          <Box component="span" sx={{flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis',
            whiteSpace: 'nowrap'}}>{item.name}</Box>
          <StatusBadge status={item.status} />
          <span>r{item.revision}</span>
        </Box>
      </Box>)}
    </Box>
  </Stack>;
}

ModelList.propTypes = {
  items: PropTypes.array.isRequired, status: PropTypes.string.isRequired, selectedId: PropTypes.string,
  onOpen: PropTypes.func.isRequired, onNew: PropTypes.func.isRequired, disabled: PropTypes.bool,
};
