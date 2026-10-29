/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useReducer, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {SecretField} from '../../primitives/Field';
import {Select} from '../../primitives/Choice';
import {Dialog} from '../../overlays/Dialog';
import {Badge, Banner} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import EmbedForm from './EmbedForm';
import EmbedPreview from './EmbedPreview';
import {
  draftFromEmbed, draftReducer, embedPermissions, initialPanel, newDraft, ownerActions, panelReducer,
  snippets, statsSummary, statusLine, toDefinition, validateDraft,
} from './embeds';

const message = (error) => error?.message || String(error);
const when = (value) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
};

const SNIPPET_LABELS = {python: () => 'Python', node: () => 'Node.js', pseudo: () => gettext('Pseudo-code')};

function Section({title, children}) {
  return <Box component="section" aria-label={title} sx={{display: 'grid', gap: 0.75}}>
    <Box component="h4" sx={{m: 0, fontSize: '0.8125rem'}}>{title}</Box>
    {children}
  </Box>;
}

Section.propTypes = {title: PropTypes.string.isRequired, children: PropTypes.node};

async function copyText(text) {
  // Deliberately not the shared clipboard helper: it keeps a copy in localStorage.
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/** The signing secret, shown once. Held in component state only. */
function SecretNotice({secret, onHide}) {
  const [copied, setCopied] = useState('');
  return <Box role="group" aria-label={gettext('Signing secret')}
    sx={{display: 'grid', gap: 0.75, border: '2px solid', borderColor: 'warning.main', p: 1}}>
    <Banner status="warning">
      {gettext('Copy this signing secret now. It is shown only once and cannot be recovered. ' +
        'Keep it on your server; anyone who has it can create valid tokens for this embed.')}
    </Banner>
    <Stack direction="row" gap="compact" sx={{alignItems: 'flex-start', flexWrap: 'wrap'}}>
      <SecretField size="small" label={gettext('Secret')} value={secret.secret} allowReveal allowCopy autoComplete="off"
        InputProps={{readOnly: true}} sx={{minWidth: 340}} />
      <Button onClick={async () => setCopied((await copyText(secret.secret)) ? 'ok' : 'failed')}>
        {gettext('Copy secret')}</Button>
      <Button intent="primary" onClick={onHide}>{gettext('I have saved it')}</Button>
    </Stack>
    <Box sx={{fontSize: '0.75rem'}}>
      {gettext('Key id (put it in the token header as "kid"): %s. Algorithm: HS256.', secret.kid)}</Box>
    {copied === 'ok' && <Box role="status" sx={{fontSize: '0.75rem'}}>{gettext('Copied.')}</Box>}
    {copied === 'failed' && <Box role="status" sx={{fontSize: '0.75rem'}}>
      {gettext('Copying was blocked. Reveal the secret and copy it by hand.')}</Box>}
  </Box>;
}

SecretNotice.propTypes = {secret: PropTypes.object.isRequired, onHide: PropTypes.func.isRequired};

function Stats({stats, onClose}) {
  const summary = statsSummary(stats.data);
  return <Box component="section" aria-label={gettext('Views')}
    sx={{display: 'grid', gap: 0.5, border: '1px solid', borderColor: 'divider', p: 1}}>
    <Stack direction="row" gap="compact" sx={{alignItems: 'center'}}>
      <Box component="h4" sx={{m: 0, fontSize: '0.8125rem', flex: 1}}>{gettext('Views in the last 30 days')}</Box>
      <Button size="small" onClick={onClose}>{gettext('Close')}</Button>
    </Stack>
    {stats.status === 'loading' && <Box role="status" sx={{fontSize: '0.75rem'}}>{gettext('Loading...')}</Box>}
    {stats.status === 'error' && <Banner status="error">{stats.error}</Banner>}
    {stats.status === 'ready' && <>
      <Box sx={{fontSize: '0.8125rem'}}>
        {gettext('%s views, %s card runs, %s errors.', summary.totals.views, summary.totals.cardRuns, summary.totals.errors)}
      </Box>
      {summary.rows.length > 0 && <Box component="table" aria-label={gettext('Views per day')}
        sx={{borderCollapse: 'collapse', fontSize: '0.75rem'}}>
        <thead><tr>
          <Box component="th" scope="col" sx={{textAlign: 'left', pr: 2}}>{gettext('Day')}</Box>
          <Box component="th" scope="col" sx={{textAlign: 'right', pr: 2}}>{gettext('Views')}</Box>
          <Box component="th" scope="col" sx={{textAlign: 'right', pr: 2}}>{gettext('Card runs')}</Box>
          <Box component="th" scope="col" sx={{textAlign: 'right'}}>{gettext('Errors')}</Box>
        </tr></thead>
        <tbody>{summary.rows.map((row) => <tr key={row.day}>
          <td>{row.day}</td>
          <Box component="td" sx={{textAlign: 'right', pr: 2}}>{row.views}</Box>
          <Box component="td" sx={{textAlign: 'right', pr: 2}}>{row.cardRuns}</Box>
          <Box component="td" sx={{textAlign: 'right'}}>{row.errors}</Box>
        </tr>)}</tbody>
      </Box>}
      <Box sx={{fontSize: '0.7rem', color: 'text.secondary'}}>
        {gettext('Only counts are kept: no viewer, address or claim values.')}</Box>
    </>}
  </Box>;
}

Stats.propTypes = {stats: PropTypes.object.isRequired, onClose: PropTypes.func.isRequired};

function Snippets({embed, parameters, onClose}) {
  const [language, setLanguage] = useState('python');
  const draft = draftFromEmbed(embed, parameters);
  const text = snippets({embed, draft, host: typeof window === 'undefined' ? '' : window.location.origin})[language];
  return <Box component="section" aria-label={gettext('Code for the embedding site')}
    sx={{display: 'grid', gap: 0.5, border: '1px solid', borderColor: 'divider', p: 1}}>
    <Stack direction="row" gap="compact" sx={{alignItems: 'center'}}>
      <Box component="h4" sx={{m: 0, fontSize: '0.8125rem', flex: 1}}>{gettext('Signing a token for %s', embed.name)}</Box>
      <Select size="small" label={gettext('Language')} value={language} sx={{minWidth: 150}}
        options={Object.keys(SNIPPET_LABELS).map((value) => ({value, label: SNIPPET_LABELS[value]()}))}
        onChange={setLanguage} />
      <Button size="small" onClick={onClose}>{gettext('Close')}</Button>
    </Stack>
    <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
      {gettext('Sign tokens on your own server with the secret from the environment. Never put the secret in a page or an app. Use a new token for every page view and the shortest lifetime that works.')}
    </Box>
    <Box component="pre" aria-label={gettext('Example code')}
      sx={{m: 0, p: 1, overflow: 'auto', fontSize: '0.75rem', bgcolor: 'action.hover'}}>{text}</Box>
  </Box>;
}

Snippets.propTypes = {embed: PropTypes.object.isRequired, parameters: PropTypes.array, onClose: PropTypes.func.isRequired};

function EmbedRow({embed, busy, confirming, onAct, onEdit, onConfirm, onPreview, onStats, onSnippets}) {
  const status = statusLine(embed);
  const actions = ownerActions(embed);
  const delegation = embed.run_as?.delegation;
  const act = (key, work) => onAct(`${key}-${embed.embed_id}`, work);
  const confirmable = (key, label, work, intent) => <Button size="small" intent={intent} disabled={busy}
    aria-label={confirming === `${key}-${embed.embed_id}` ? gettext('Confirm %s %s', label, embed.name) :
      `${label} ${embed.name}`}
    onClick={() => (confirming === `${key}-${embed.embed_id}` ?
      act(key, work) : onConfirm(`${key}-${embed.embed_id}`))}>
    {confirming === `${key}-${embed.embed_id}` ? gettext('Confirm') : label}</Button>;
  return <Box component="li" aria-label={embed.name}
    sx={{display: 'grid', gap: 0.5, py: 0.75, borderBottom: '1px solid', borderColor: 'divider'}}>
    <Stack direction="row" gap="compact" sx={{alignItems: 'center', flexWrap: 'wrap'}}>
      <Box sx={{flex: 1, minWidth: 160}}><strong>{embed.name}</strong></Box>
      <Badge status={status.tone} label={status.label} />
    </Stack>
    {status.detail && <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>{status.detail}</Box>}
    <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
      {gettext('Owner: %s', embed.owner_name)}
      {' · '}{embed.definition.origins.length ? embed.definition.origins.join(', ') : gettext('no site may frame it')}
      {' · '}{gettext('tokens up to %s s', embed.definition.max_token_lifetime_seconds)}
      {embed.is_owner && embed.keys.length > 0 && ` · ${gettext('keys: %s', embed.keys.map((key) =>
        `${key.kid} (${key.slot === 'current' ? gettext('current') : gettext('previous')})`).join(', '))}`}
      {delegation && ` · ${gettext('runs as you until %s', when(delegation.expires_at))}`}
    </Box>
    {!embed.is_owner && <Box sx={{fontSize: '0.7rem', color: 'text.secondary'}}>
      {gettext('Owned by someone else. You can disable or revoke it and see its view counts.')}</Box>}
    <Stack direction="row" gap="compact" sx={{flexWrap: 'wrap'}}>
      {actions.edit && <Button size="small" disabled={busy} aria-label={gettext('Edit %s', embed.name)}
        onClick={() => onEdit(embed)}>{gettext('Edit')}</Button>}
      {actions.enable && <Button size="small" disabled={busy} aria-label={gettext('Enable %s', embed.name)}
        onClick={() => act('enable', (client) => client.enableEmbed(embed.embed_id))}>{gettext('Enable')}</Button>}
      {actions.disable && <Button size="small" disabled={busy} aria-label={gettext('Disable %s', embed.name)}
        onClick={() => act('disable', (client) => client.disableEmbed(embed.embed_id))}>{gettext('Disable')}</Button>}
      {actions.preview && <Button size="small" disabled={busy} aria-label={gettext('Preview %s', embed.name)}
        onClick={() => onPreview(embed)}>{gettext('Preview')}</Button>}
      {embed.is_owner && embed.status !== 'revoked' && <Button size="small" aria-label={gettext('Code for %s', embed.name)}
        onClick={() => onSnippets(embed)}>{gettext('Code')}</Button>}
      {actions.rotate && confirmable('rotate', gettext('Rotate key'), (client) => client.rotateEmbedKey(embed.embed_id))}
      {actions.retire && <Button size="small" disabled={busy} aria-label={gettext('Retire old key of %s', embed.name)}
        onClick={() => act('retire', (client) => client.retireEmbedKey(embed.embed_id))}>{gettext('Retire old key')}</Button>}
      <Button size="small" aria-label={gettext('Views of %s', embed.name)} onClick={() => onStats(embed)}>
        {gettext('Views')}</Button>
      {actions.revoke && confirmable('revoke', gettext('Revoke'), (client) => client.revokeEmbed(embed.embed_id), 'destructive')}
      {actions.remove && confirmable('delete', gettext('Delete'), (client) => client.deleteEmbed(embed.embed_id), 'destructive')}
    </Stack>
  </Box>;
}

EmbedRow.propTypes = {
  embed: PropTypes.object.isRequired, busy: PropTypes.bool, confirming: PropTypes.string,
  onAct: PropTypes.func.isRequired, onEdit: PropTypes.func.isRequired, onConfirm: PropTypes.func.isRequired,
  onPreview: PropTypes.func.isRequired, onStats: PropTypes.func.isRequired, onSnippets: PropTypes.func.isRequired,
};

/**
 * Signed embedding of one saved question or dashboard
 * (docs/en_US/bi_embedding.rst). The list shows every embed of the resource
 * the caller manages; the server decides each action again.
 */
export default function EmbedDialog({
  client, resourceType, resourceId, resourceName, access = 'manage', parameters = [], rawSql = false, onClose,
}) {
  const [state, dispatch] = useReducer(panelReducer, undefined, initialPanel);
  const [draft, draftDispatch] = useReducer(draftReducer, null);
  const [catalog, setCatalog] = useState(null);
  const [showErrors, setShowErrors] = useState(false);
  const [confirming, setConfirming] = useState('');
  const [previewing, setPreviewing] = useState(null);
  const [coding, setCoding] = useState(null);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  const load = useCallback(async () => {
    try {
      const items = await client.listEmbeds(resourceType, resourceId);
      if(alive.current) dispatch({type: 'loaded', items});
    } catch(error) {
      if(alive.current) dispatch({type: 'failed', error: message(error)});
    }
  }, [client, resourceType, resourceId]);
  useEffect(() => {
    dispatch({type: 'loading'});
    client.embedCatalog().then(
      (value) => {
        if(!alive.current) return;
        setCatalog(value);
        if(value.available) load();
        else dispatch({type: 'loaded', items: []});
      },
      (error) => { if(alive.current) dispatch({type: 'failed', error: message(error)}); });
  }, [client, load]);

  const permissions = embedPermissions(access, {available: Boolean(catalog?.available)});
  const errors = draft && catalog ? validateDraft(draft, catalog) : {};
  const shownErrors = showErrors ? errors : {};

  const act = async (key, work) => {
    setConfirming('');
    dispatch({type: 'busy', key});
    try {
      const outcome = await work(client);
      if(!alive.current) return;
      if(key.startsWith('rotate-') && outcome?.secret) {
        dispatch({type: 'secretShown', embedId: outcome.embed.embed_id, kid: outcome.secret.kid,
          secret: outcome.secret.secret});
        dispatch({type: 'notice', text: gettext('A new key is current. The old key keeps working until you retire it or rotate again.')});
      } else if(key.startsWith('enable-')) {
        dispatch({type: 'notice', text: gettext('Enabled. It runs with your database access until the authorization expires.')});
      } else {
        dispatch({type: 'notice', text: ''});
      }
      await load();
    } catch(error) {
      if(alive.current) dispatch({type: 'failed', error: message(error)});
    }
  };

  const startNew = () => {
    draftDispatch({type: 'reset', draft: newDraft({
      resourceType, resourceId, resourceName: gettext('%s embed', resourceName), parameters,
      lifetime: Math.min(600, catalog?.max_token_lifetime_seconds || 600)})});
    setShowErrors(false);
    dispatch({type: 'edit', id: 'new'});
  };
  const edit = (embed) => {
    draftDispatch({type: 'reset', draft: draftFromEmbed(embed, parameters)});
    setShowErrors(false);
    dispatch({type: 'edit', id: embed.embed_id});
  };
  const closeEditor = () => {
    draftDispatch({type: 'reset', draft: null});
    dispatch({type: 'closeEditor'});
  };

  const save = async () => {
    if(Object.keys(errors).length) { setShowErrors(true); return; }
    dispatch({type: 'busy', key: 'save'});
    try {
      if(draft.embedId) {
        await client.updateEmbed(draft.embedId, draft.revision, toDefinition(draft));
        dispatch({type: 'notice', text: gettext('Saved.')});
      } else {
        const made = await client.createEmbed(toDefinition(draft));
        dispatch({type: 'secretShown', embedId: made.embed.embed_id, kid: made.secret.kid, secret: made.secret.secret});
        dispatch({type: 'notice', text: gettext('Created, but not enabled yet. Copy the secret, then enable the embed.')});
      }
      if(!alive.current) return;
      closeEditor();
      await load();
    } catch(error) {
      if(alive.current) dispatch({type: 'failed', error: message(error)});
    }
  };

  const openStats = async (embed) => {
    if(state.stats.id === embed.embed_id) { dispatch({type: 'statsClosed'}); return; }
    dispatch({type: 'statsLoading', id: embed.embed_id});
    try {
      const data = await client.embedStats(embed.embed_id, 30);
      if(alive.current) dispatch({type: 'statsLoaded', id: embed.embed_id, data});
    } catch(error) {
      if(alive.current) dispatch({type: 'statsFailed', id: embed.embed_id, error: message(error)});
    }
  };

  const busy = state.busy !== '';
  const editing = state.editing !== null && draft !== null;
  const previewEmbed = previewing && state.items.find((item) => item.embed_id === previewing);
  const codeEmbed = coding && state.items.find((item) => item.embed_id === coding);

  return <Dialog open size="large" busy={busy} title={gettext('Embed %s', resourceName)} onClose={() => onClose?.()}
    actions={<>
      <Button disabled={!permissions.canCreate || editing} onClick={startNew}>{gettext('New embed')}</Button>
      <Button onClick={() => onClose?.()}>{gettext('Close')}</Button>
    </>}>
    <Box data-cdeadmin-qa-key="bi.embed" sx={{display: 'grid', gap: 1.25}}>
      {catalog && !catalog.available && <Banner status="warning">
        {gettext('Signed embedding is not enabled on this server. An administrator turns it on with CDEADMIN_BI_EMBED_ENABLED and a worker key ring.')}
      </Banner>}
      <Banner status="info">
        {gettext('An embedded view needs no sign-in. It runs with your own database access (as the "embedding" principal) ' +
          'and shows what this content shows to anyone holding a token that your server signed. ' +
          'Row policies see only the claims inside the token, never your identity. Raw SQL questions need the server to allow them.')}
      </Banner>
      {rawSql && <Banner status="warning">
        {gettext('This content uses raw SQL. Raw SQL cannot be filtered by claims, and the server refuses it unless the administrator allows it.')}
      </Banner>}
      {state.error && <Banner status="error" onClose={() => dispatch({type: 'dismiss'})}>{state.error}</Banner>}
      {state.notice && <Banner status="info" onClose={() => dispatch({type: 'dismiss'})}>{state.notice}</Banner>}
      {state.secret && <SecretNotice secret={state.secret} onHide={() => dispatch({type: 'secretHidden'})} />}
      {state.status === 'loading' && <Box role="status" sx={{fontSize: '0.75rem'}}>{gettext('Loading...')}</Box>}
      {catalog?.available && state.status === 'ready' && state.items.length === 0 && !editing &&
        <EmptyState message={gettext('No embeds yet.')} />}
      {state.items.length > 0 && <Box component="ul" aria-label={gettext('Embeds')} sx={{m: 0, p: 0, listStyle: 'none'}}>
        {state.items.map((embed) => <EmbedRow key={embed.embed_id} embed={embed} busy={busy} confirming={confirming}
          onAct={act} onEdit={edit} onConfirm={setConfirming}
          onPreview={(item) => { setPreviewing(item.embed_id); setCoding(null); }}
          onSnippets={(item) => { setCoding(item.embed_id); setPreviewing(null); }}
          onStats={openStats} />)}
      </Box>}
      {state.stats.status !== 'idle' && <Stats stats={state.stats} onClose={() => dispatch({type: 'statsClosed'})} />}
      {codeEmbed && <Snippets embed={codeEmbed} parameters={parameters} onClose={() => setCoding(null)} />}
      {previewEmbed && <EmbedPreview client={client} embed={previewEmbed} onClose={() => setPreviewing(null)}
        draft={draftFromEmbed(previewEmbed, parameters)} />}
      {editing && <Section title={draft.embedId ? gettext('Edit embed') : gettext('New embed')}>
        <EmbedForm draft={draft} dispatch={draftDispatch} errors={shownErrors} catalog={catalog || {}} rawSql={rawSql} />
        <Stack direction="row" gap="compact">
          <Button intent="primary" loading={state.busy === 'save'} onClick={save}>
            {draft.embedId ? gettext('Save changes') : gettext('Create embed')}</Button>
          <Button onClick={closeEditor}>{gettext('Cancel')}</Button>
        </Stack>
        {showErrors && Object.keys(errors).length > 0 && <Banner status="warning">
          {gettext('Fix the marked fields first.')}</Banner>}
      </Section>}
    </Box>
  </Dialog>;
}

EmbedDialog.propTypes = {
  client: PropTypes.object.isRequired,
  resourceType: PropTypes.oneOf(['question', 'dashboard']).isRequired,
  resourceId: PropTypes.string.isRequired,
  resourceName: PropTypes.string.isRequired,
  access: PropTypes.string,
  parameters: PropTypes.array,
  rawSql: PropTypes.bool,
  onClose: PropTypes.func,
};
