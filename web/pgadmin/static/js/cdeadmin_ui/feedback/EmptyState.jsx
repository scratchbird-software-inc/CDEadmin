/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import PropTypes from 'prop-types';
import {styled} from '@mui/material/styles';
import {Box} from '@mui/material';
import InfoRoundedIcon from '@mui/icons-material/InfoRounded';
import {Button} from '../primitives/Button';

const Root = styled(Box)(({theme}) => ({
  color: theme.palette.text.primary,
  margin: '24px auto 12px',
  fontSize: '0.8rem',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  flexDirection: 'column',
  gap: theme.spacing(0.5),
  minHeight: 'var(--cde-target-size, 24px)',
  width: '100%',
  maxWidth: '100%',
  minWidth: 0,
  boxSizing: 'border-box',
  paddingInline: theme.spacing(1),
}));

export function EmptyState({message, icon, actionLabel, onAction, style,
  ...props}) {
  return <Root data-cde-empty-state="true" style={style} {...props}>
    <Box sx={{display: 'flex', alignItems: 'center', gap: 0.5,
      width: '100%', maxWidth: 520, minWidth: 0, textAlign: 'center',
      '& > svg': {flexShrink: 0}}}>
      {icon ?? <InfoRoundedIcon aria-hidden="true" style={{height: '1.2rem'}} />}
      <Box component="span" sx={{minWidth: 0, overflowWrap: 'anywhere'}}>
        {message}</Box>
    </Box>
    {actionLabel && <Button onClick={onAction}>{actionLabel}</Button>}
  </Root>;
}

EmptyState.propTypes = {
  message: PropTypes.node,
  icon: PropTypes.node,
  actionLabel: PropTypes.node,
  onAction: PropTypes.func,
  style: PropTypes.object,
};
