/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import getApiInstance from 'sources/api_instance';
import {Box, Grid, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {TextField} from '../../primitives/Field';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
import {SqliteSectionCard, createSqliteWorkspaceCaller} from './sqliteAdminHelpers';

const textVal = (e) => (e?.target ? e.target.value : String(e ?? ''));

/**
 * SQ-AUD-10 (SR-F-030561): Native SQLite Expert Index Advisor (Preview-Only).
 */
export default function SqliteExpertWorkspace({
  endpointUrl,
  databaseTargetId = '',
  api: injectedApi = null,
}) {
  const api = useMemo(() => injectedApi || getApiInstance(), [injectedApi]);
  const callSqlite = useMemo(
    () => createSqliteWorkspaceCaller(api, endpointUrl, databaseTargetId),
    [api, endpointUrl, databaseTargetId]
  );

  const [status, setStatus] = useState(null);
  const [querySql, setQuerySql] = useState('SELECT * FROM sqlite_schema;');
  const [samplePercent, setSamplePercent] = useState('25');
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadStatus = useCallback(async () => {
    try {
      const s = await callSqlite({action: 'sqlite_ops_expert_status'});
      setStatus(s);
    } catch (err) {
      setError(err?.message || String(err));
    }
  }, [callSqlite]);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const handleAnalyze = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callSqlite({
        action: 'sqlite_ops_expert_analyze',
        request: {
          queries: [querySql],
          sample_percent: Number(samplePercent) || 0,
        },
      });
      setReport(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box style={{padding: 16}}>
      <Stack gap="md">
        <Stack direction="row" gap="sm" style={{justifyContent: 'space-between', alignItems: 'center'}}>
          <Stack direction="row" gap="sm" style={{alignItems: 'center'}}>
            <strong>{gettext('SQLite Expert Index Advisor')}</strong>
            <Badge status="info" label={gettext('Experimental Preview-Only')} />
          </Stack>
          <FormReference reference="SR-F-030561" />
        </Stack>

        <Banner status="warning">
          {gettext('SQLite ext/expert analyzes query plans against a read-only connection and never creates indexes automatically. Review recommended CREATE INDEX DDL before applying.')}
        </Banner>

        {error && <ValidationMessage status="error">{error}</ValidationMessage>}

        <SqliteSectionCard
          title={gettext('Workload Query & Sampling Budget')}
          actions={
            <Badge
              status={status?.available ? 'success' : 'warning'}
              label={status?.available ? gettext('Expert C Bridge Ready') : gettext('Bridge Unavailable')}
            />
          }
        >
          <CodeEditor
            language="sql"
            value={querySql}
            onChange={(val) => setQuerySql(val)}
            minHeight={110}
          />
          <Grid columns={2} gap="sm">
            <TextField
              label={gettext('Statistic Sample Percentage (0-100)')}
              value={samplePercent}
              onChange={(e) => setSamplePercent(textVal(e))}
            />
            <div style={{display: 'flex', alignItems: 'flex-end'}}>
              <Button variant="primary" disabled={busy || !querySql.trim()} onClick={handleAnalyze}>
                {gettext('Analyze Candidate Indexes')}
              </Button>
            </div>
          </Grid>
        </SqliteSectionCard>

        {report && (
          <SqliteSectionCard title={gettext('Recommended Indexes & Simulated Query Plans')}>
            <div>
              {gettext('Indexes Applied Automatically')}: <strong>{String(report.indexes_applied)}</strong>
            </div>
            {(report.statements || []).map((stmt) => (
              <Stack key={stmt.ordinal} gap="sm">
                <strong>{gettext('Statement')} #{stmt.ordinal + 1}: {stmt.sql}</strong>
                <pre style={{margin: 0, whiteSpace: 'pre-wrap'}}>
                  {stmt.recommended_indexes_ddl || gettext('(No additional indexes recommended)')}
                </pre>
                <pre style={{margin: 0, whiteSpace: 'pre-wrap'}}>{stmt.query_plan}</pre>
              </Stack>
            ))}
          </SqliteSectionCard>
        )}
      </Stack>
    </Box>
  );
}

SqliteExpertWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  databaseTargetId: PropTypes.string,
  api: PropTypes.object,
};
