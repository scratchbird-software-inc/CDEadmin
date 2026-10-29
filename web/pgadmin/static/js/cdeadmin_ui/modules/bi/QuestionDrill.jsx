/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box} from '../../primitives/Layout';
import {Banner} from '../../feedback/Indicators';
import {appendPage, executionFrom} from './executionModel';
import ResultPane from './ResultPane';

const PAGE_SIZE = 100;
const message = (error) => error?.message || String(error);

/**
 * The target of a question drill-through: the pinned question run with the
 * parameters the click supplied, shown with the usual result pane.
 */
export default function QuestionDrill({client, questionId, revision, parameters, onLoaded}) {
  const [run, setRun] = useState({status: 'running', execution: null, error: ''});
  const [visualization, setVisualization] = useState({type: 'table', settings: {}});
  const [paging, setPaging] = useState(false);
  const parametersKey = JSON.stringify(parameters || {});

  useEffect(() => {
    let cancelled = false;
    setRun({status: 'running', execution: null, error: ''});
    Promise.all([
      client.executeStored(questionId, revision, {parameters: JSON.parse(parametersKey), pageSize: PAGE_SIZE}),
      client.revision(questionId, revision).catch(() => null),
    ]).then(([response, record]) => {
      if(cancelled) return;
      setRun({status: 'done', execution: executionFrom(response), error: ''});
      if(record?.definition?.visualization) setVisualization(record.definition.visualization);
      if(record?.definition?.name) onLoaded?.(record.definition.name);
    }, (error) => { if(!cancelled) setRun({status: 'error', execution: null, error: message(error)}); });
    return () => { cancelled = true; };
    // onLoaded only names the breadcrumb; changing it must not rerun the question.
  }, [client, questionId, revision, parametersKey]);

  const loadMore = useCallback(async () => {
    const current = run.execution;
    if(!current?.cursor) return;
    setPaging(true);
    try {
      const response = await client.page(current.resultId, current.cursor, PAGE_SIZE);
      setRun((now) => now.execution ? {...now, execution: appendPage(now.execution, response)} : now);
    } catch(error) {
      setRun((now) => ({...now, error: message(error)}));
    } finally {
      setPaging(false);
    }
  }, [client, run.execution]);

  return <Box data-cdeadmin-qa-key="bi.dashboard.drill" sx={{display: 'grid', gap: 1, minWidth: 0}}>
    <Banner status="info">{gettext('Opened from a dashboard drill-through with the clicked values.')}</Banner>
    <ResultPane execution={run.execution} running={run.status === 'running'} error={run.error}
      visualization={visualization} onVisualization={setVisualization}
      onLoadMore={loadMore} loadingMore={paging} />
  </Box>;
}

QuestionDrill.propTypes = {
  client: PropTypes.object.isRequired,
  questionId: PropTypes.string.isRequired,
  revision: PropTypes.number.isRequired,
  parameters: PropTypes.object,
  onLoaded: PropTypes.func,
};
