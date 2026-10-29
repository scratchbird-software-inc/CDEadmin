/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../../../primitives/Layout';
import {Button} from '../../../primitives/Button';
import {Banner} from '../../../feedback/Indicators';
import {EmptyState} from '../../../feedback/EmptyState';
import {Dialog} from '../../../overlays/Dialog';
import {makePost} from '../../../objects/ProviderObjectEditorHost';
import ModelEditor from './ModelEditor';
import ModelList from './ModelList';
import {createModelsClient} from './modelsClient';
import useModelSession from './useModelSession';

/**
 * The Models view of the BI module: the endpoint's semantic models and the editor for the open one.
 * It is given the workspace `post` ({action, request} -> data) directly, or an `api` and
 * `endpointUrl` to build one, and talks to the semantic_*, report_scheduler_* and migration actions only.
 */
export default function BIModelsTool({post, api, endpointUrl, client: suppliedClient, onDirtyChange}) {
  const client = useMemo(() => suppliedClient || createModelsClient(post || makePost(api, endpointUrl)),
    [suppliedClient, post, api, endpointUrl]);
  const session = useModelSession(client, {onDirtyChange});
  const [pending, setPending] = useState(null);
  const {state, list, busy} = session;

  // leaving unsaved edits asks first; the question is plain data, never a stored function
  const guarded = (intent) => state.dirty ? setPending(intent) : perform(intent);
  const perform = async (intent) => {
    setPending(null);
    if(intent.kind === 'new') session.startNew();
    else await session.open(intent.modelId);
  };

  return <Box sx={{display: 'flex', height: '100%', minHeight: 0, overflow: 'hidden'}} data-cdeadmin-qa-key="bi.models">
    <Box sx={{borderRight: '1px solid', borderColor: 'divider', overflow: 'auto', flexShrink: 0}}>
      <ModelList items={list.items} status={list.status} selectedId={state.record?.model_id}
        disabled={busy !== ''} onNew={() => guarded({kind: 'new'})}
        onOpen={(modelId) => guarded({kind: 'open', modelId})} />
    </Box>
    <Box sx={{flex: 1, minWidth: 0, overflow: 'auto'}}>
      {!state.draft ?
        <Stack gap="standard" sx={{p: 2}}>
          {session.error && <Banner status="error">{session.error}</Banner>}
          <EmptyState message={list.status === 'ready' && !list.items.length ?
            gettext('Create the first semantic model to get started.') :
            gettext('Choose a semantic model, or start a new one.')} />
        </Stack> :
        <ModelEditor client={client} session={session} />}
    </Box>
    <Dialog open={Boolean(pending)} title={gettext('Discard unsaved changes?')} onClose={() => setPending(null)}
      actions={<Stack direction="row" gap="compact">
        <Button onClick={() => setPending(null)}>{gettext('Keep editing')}</Button>
        <Button intent="destructive" onClick={() => perform(pending)}>{gettext('Discard changes')}</Button>
      </Stack>}>
      {gettext('The open model has edits that were not saved. Opening another model discards them.')}
    </Dialog>
  </Box>;
}

BIModelsTool.propTypes = {
  post: PropTypes.func, api: PropTypes.object, endpointUrl: PropTypes.string, client: PropTypes.object,
  onDirtyChange: PropTypes.func,
};
