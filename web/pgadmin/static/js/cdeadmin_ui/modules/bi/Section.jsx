/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useId} from 'react';
import PropTypes from 'prop-types';
import {Box, Stack} from '../../primitives/Layout';
import {ValidationMessage} from '../../feedback/Indicators';

/** A titled group of builder controls with an optional validation message. */
export default function Section({title, children, actions, error, qaKey}) {
  const headingId = useId();
  return <Box component="section" aria-labelledby={headingId} data-cdeadmin-qa-key={qaKey}
    sx={{border: '1px solid', borderColor: error ? 'error.main' : 'divider', p: 1, minWidth: 0}}>
    <Stack direction="row" gap="compact" sx={{alignItems: 'center', mb: 1}}>
      <Box id={headingId} component="h3" sx={{m: 0, flex: 1, fontSize: '0.8125rem', fontWeight: 600}}>
        {title}
      </Box>
      {actions}
    </Stack>
    {children}
    {error && <ValidationMessage>{error}</ValidationMessage>}
  </Box>;
}

Section.propTypes = {
  title: PropTypes.node.isRequired,
  children: PropTypes.node,
  actions: PropTypes.node,
  error: PropTypes.string,
  qaKey: PropTypes.string,
};
