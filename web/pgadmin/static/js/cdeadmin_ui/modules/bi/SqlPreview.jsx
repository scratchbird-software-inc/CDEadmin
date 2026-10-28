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
import {Box} from '../../primitives/Layout';
import {Banner} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import CodeEditor from '../../editors/CodeEditor';

/**
 * The SQL the provider compiles for the current question. It is a preview
 * with values written as literals; Run always executes the bound form.
 */
export default function SqlPreview({preview}) {
  const {status, compiled, error} = preview;
  return <Box data-cdeadmin-qa-key="bi.sql-preview" sx={{display: 'grid', gap: 1}}>
    {status === 'idle' && <EmptyState message={gettext('Choose what to show and the compiled SQL appears here.')} />}
    {status === 'loading' && <Box role="status" sx={{fontSize: '0.75rem'}}>{gettext('Compiling...')}</Box>}
    {status === 'error' && <Banner status="error">{error}</Banner>}
    {compiled && <>
      <Box sx={{height: 200}}>
        <CodeEditor label={gettext('Compiled SQL')} language="sql" readonly value={String(compiled.source ?? '')} />
      </Box>
      {(compiled.warnings || []).map((warning) => <Banner key={warning} status="info">{warning}</Banner>)}
      <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
        {gettext('Preview only: values are shown as literals. Running the question sends them as bound parameters.')}
      </Box>
    </>}
  </Box>;
}

SqlPreview.propTypes = {
  preview: PropTypes.shape({
    status: PropTypes.oneOf(['idle', 'loading', 'ready', 'error']).isRequired,
    compiled: PropTypes.object, error: PropTypes.string,
  }).isRequired,
};
