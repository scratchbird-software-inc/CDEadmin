/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {Breadcrumbs} from '../../navigation/TabsAndBreadcrumbs';
import DashboardView from './DashboardView';
import QuestionDrill from './QuestionDrill';

/**
 * The viewer with drill-through navigation. The trail starts at the open
 * dashboard; a drill-through to another dashboard or to a question pushes a
 * level and the breadcrumb (or Back) returns to an earlier one with the
 * filter values and tab it was left with.
 */
export default function DashboardViewer({client, dashboardId, name}) {
  const [trail, setTrail] = useState([{kind: 'dashboard', dashboardId, name: name || ''}]);
  const index = trail.length - 1;
  const top = trail[index];

  const drill = useCallback((target, context) => {
    setTrail((current) => {
      const last = current.length - 1;
      const left = current.map((entry, position) => position === last ?
        {...entry, resume: {values: context.values, tabId: context.tabId}} : entry);
      if(target.kind === 'dashboard') {
        return [...left, {kind: 'dashboard', dashboardId: target.dashboard_id, name: '',
          initial: {values: target.resolved?.filters ?? target.filters}}];
      }
      return [...left, {kind: 'question', questionId: target.question_id, revision: target.revision,
        parameters: target.parameters, name: context.label || ''}];
    });
  }, []);

  const rename = useCallback((position, label) => setTrail((current) => current.map((entry, at) =>
    at === position && label && entry.name !== label ? {...entry, name: label} : entry)), []);

  const back = (to) => setTrail((current) => current.slice(0, to + 1));
  const crumbs = trail.map((entry, position) => ({
    id: position,
    label: entry.name || (entry.kind === 'question' ? gettext('Question') : gettext('Dashboard')),
  }));

  return <Box data-cdeadmin-qa-key="bi.dashboard.viewer" sx={{display: 'grid', gap: 1, minWidth: 0}}>
    {trail.length > 1 && <Stack direction="row" gap="compact" sx={{alignItems: 'center'}}>
      <Button size="small" onClick={() => back(index - 1)}>{gettext('Back')}</Button>
      <Breadcrumbs items={crumbs} onNavigate={(item) => back(item.id)} />
    </Stack>}
    {top.kind === 'dashboard' ?
      <DashboardView key={`${index}:${top.dashboardId}`} client={client} dashboardId={top.dashboardId}
        initial={top.resume || top.initial} onDrill={drill}
        onLoaded={(record) => rename(index, record.definition?.name)} /> :
      <QuestionDrill key={`${index}:${top.questionId}`} client={client} questionId={top.questionId}
        revision={top.revision} parameters={top.parameters}
        onLoaded={(label) => rename(index, label)} />}
  </Box>;
}

DashboardViewer.propTypes = {
  client: PropTypes.object.isRequired,
  dashboardId: PropTypes.string.isRequired,
  name: PropTypes.string,
};
