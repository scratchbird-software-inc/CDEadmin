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
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {Banner, ValidationMessage} from '../../feedback/Indicators';
import CodeEditor from '../../editors/CodeEditor';
import Section from './Section';

function LossList({loss}) {
  if(!loss.length) return null;
  return <Box component="ul" aria-label={gettext('Differences between the SQL and the builder')}
    sx={{m: 0, pl: 3, fontSize: '0.8125rem'}}>
    {loss.map((item, index) => <li key={`${item.code}-${index}`}>
      <strong>{item.severity === 'blocking' ? gettext('Cannot convert') : item.severity === 'warning' ?
        gettext('Changes the query') : gettext('Note')}</strong>{': '}{item.detail}
    </li>)}
  </Box>;
}

LossList.propTypes = {loss: PropTypes.array.isRequired};

/**
 * Report of bi_sql_to_question: exact mappings may switch to the builder
 * directly, lossy ones only after the differences are shown and accepted,
 * and unmappable statements stay SQL with the blocking reasons listed.
 */
export function ConversionReport({outcome, onSwitch}) {
  if(!outcome) return null;
  const {fidelity, loss} = outcome;
  return <Box role="region" aria-label={gettext('Conversion to the builder')}
    sx={{display: 'grid', gap: 1, border: '1px solid', borderColor: 'divider', p: 1}}>
    {fidelity === 'exact' && <Banner status="success">
      {gettext('The builder reproduces this statement exactly.')}
    </Banner>}
    {fidelity === 'lossy' && <Banner status="warning">
      {gettext('The builder can express this statement only with the differences below.')}
    </Banner>}
    {fidelity === 'none' && <Banner status="info">
      {gettext('This statement cannot be shown in the builder, so it stays SQL.')}
    </Banner>}
    <LossList loss={loss} />
    {fidelity !== 'none' && <Stack direction="row">
      <Button intent={fidelity === 'exact' ? 'primary' : 'neutral'} onClick={() => onSwitch(outcome.question)}>
        {fidelity === 'exact' ? gettext('Switch to builder') : gettext('Switch to builder and accept the differences')}
      </Button>
    </Stack>}
  </Box>;
}

ConversionReport.propTypes = {
  outcome: PropTypes.shape({fidelity: PropTypes.string.isRequired, loss: PropTypes.array.isRequired,
    question: PropTypes.object}),
  onSwitch: PropTypes.func.isRequired,
};

/** Shown in place of the SQL text when the caller may run a question but not read it. */
export function RedactedSql() {
  return <Section title={gettext('SQL')} qaKey="bi.sql">
    <Banner status="info">
      {gettext('The SQL of this question is hidden. You can run it and use the results; ' +
        'reading or changing the statement needs edit access.')}
    </Banner>
  </Section>;
}

/** Raw SQL editor with the SQL-to-question conversion. */
export default function SqlPanel({sql, onChange, onConvert, onSwitch, error, readOnly = false}) {
  const [outcome, setOutcome] = useState(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState('');
  // A report describes one statement; editing it makes the report stale.
  useEffect(() => { setOutcome(null); setFailure(''); }, [sql]);
  const convert = async () => {
    setBusy(true);
    setFailure('');
    try {
      setOutcome(await onConvert(sql));
    } catch(caught) {
      setFailure(caught?.message || String(caught));
    } finally {
      setBusy(false);
    }
  };
  return <Section title={gettext('SQL')} error={error} qaKey="bi.sql"
    actions={<Button size="small" loading={busy} disabled={readOnly || !sql.trim()} onClick={convert}>
      {gettext('Convert to builder')}
    </Button>}>
    <Box sx={{height: 220, mb: 1}}>
      <CodeEditor label={gettext('SQL statement')} language="sql" value={sql} onChange={onChange}
        readonly={readOnly} />
    </Box>
    {failure && <ValidationMessage>{failure}</ValidationMessage>}
    <ConversionReport outcome={outcome} onSwitch={onSwitch} />
  </Section>;
}

SqlPanel.propTypes = {
  sql: PropTypes.string.isRequired,
  onChange: PropTypes.func.isRequired,
  onConvert: PropTypes.func.isRequired,
  onSwitch: PropTypes.func.isRequired,
  error: PropTypes.string,
  readOnly: PropTypes.bool,
};
