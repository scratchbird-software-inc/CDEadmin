/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useReducer, useRef} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {Dialog} from '../../overlays/Dialog';
import {Badge, Banner} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import {
  LEVEL_OPTIONS, accessRows, canAdd, canTransfer, grantable, initialShare, ownerCandidates, shareReducer,
} from './sharing';

const SEARCH_DELAY = 200;
const message = (error) => error?.message || String(error);

const levelOptions = () => LEVEL_OPTIONS.map((option) => ({value: option.value, label: gettext(option.label)}));
const levelName = (level) => gettext(LEVEL_OPTIONS.find((option) => option.value === level)?.label || level);
const kindLabel = (type) => type === 'role' ? gettext('Role') : gettext('User');

const KIND_TITLE = {
  question: () => gettext('Share question'),
  dashboard: () => gettext('Share dashboard'),
  collection: () => gettext('Share collection'),
};

function Section({title, children}) {
  return <Box component="section" aria-label={title} sx={{display: 'grid', gap: 0.75}}>
    <Box component="h4" sx={{m: 0, fontSize: '0.8125rem'}}>{title}</Box>
    {children}
  </Box>;
}

Section.propTypes = {title: PropTypes.string.isRequired, children: PropTypes.node};

function PrincipalList({label, items, onPick}) {
  if(!items.length) return null;
  return <Box component="ul" aria-label={label}
    sx={{m: 0, p: 0, listStyle: 'none', maxHeight: 160, overflow: 'auto', border: '1px solid', borderColor: 'divider'}}>
    {items.map((item) => <li key={`${item.type}-${item.id}`}>
      <Button size="small" aria-label={gettext('Choose %s %s', kindLabel(item.type), item.name)}
        onClick={() => onPick(item)}>{item.name}{' '}({kindLabel(item.type)})</Button>
    </li>)}
  </Box>;
}

PrincipalList.propTypes = {
  label: PropTypes.string.isRequired, items: PropTypes.array.isRequired, onPick: PropTypes.func.isRequired,
};

/**
 * Who can see, edit or manage one collection, question or dashboard at this
 * endpoint: find a user or role, give a level, change or remove a direct
 * grant, see what is inherited from containing collections (and stop
 * inheriting), and hand ownership to someone else after typing the name.
 *
 * Sharing never lends out data access. People you share a question with run
 * it with their own database permissions and row policies.
 */
export default function ShareDialog({client, resourceType, resourceId, resourceName, hasCollection = true, onClose, onChanged}) {
  const [state, dispatch] = useReducer(shareReducer, undefined, initialShare);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  const load = useCallback(async () => {
    try {
      const listing = await client.listGrants(resourceType, resourceId);
      if(alive.current) dispatch({type: 'loaded', listing});
    } catch(error) {
      if(alive.current) dispatch({type: 'failed', error: message(error)});
    }
  }, [client, resourceType, resourceId]);
  useEffect(() => { load(); }, [load]);

  // Principal search, debounced; an empty box lists everyone the caller may see.
  const text = state.search.text;
  const searchRequested = state.search.status === 'loading';
  useEffect(() => {
    if(!searchRequested) return undefined;
    let cancelled = false;
    const timer = setTimeout(() => {
      client.searchPrincipals(text, {limit: 20}).then(
        (results) => { if(!cancelled) dispatch({type: 'searchDone', results}); },
        (error) => { if(!cancelled) dispatch({type: 'searchFailed', error: message(error)}); });
    }, SEARCH_DELAY);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [client, text, searchRequested]);

  const attempt = async (key, work, done) => {
    dispatch({type: 'busy', key});
    try {
      await work();
      done?.();
      onChanged?.();
      await load();
    } catch(error) {
      if(alive.current) dispatch({type: 'failed', error: message(error)});
    }
  };

  const listing = state.listing;
  const rows = accessRows(listing);
  const results = grantable(state);
  const owners = ownerCandidates(state);
  const busy = state.busy !== '';

  const add = () => attempt('add', () => client.addGrant(
    resourceType, resourceId, state.pick.type, state.pick.id, state.level), () => dispatch({type: 'added'}));
  const transfer = () => attempt('transfer', async () => {
    await client.transferOwner(resourceType, resourceId, state.newOwner.id, state.confirm);
    onClose({transferred: true});
  });

  return <Dialog open title={KIND_TITLE[resourceType]()} size="large" onClose={() => onClose({})}
    actions={<Button onClick={() => onClose({})}>{gettext('Close')}</Button>}>
    <Box data-cdeadmin-qa-key="bi.share" sx={{display: 'grid', gap: 1.5}}>
      <Box sx={{fontSize: '0.8125rem'}}>{gettext('Sharing %s', resourceName)}</Box>
      <Banner status="info">
        {gettext('People you share with run this with their own database permissions and row policies. ' +
          'Sharing does not give them yours, and viewers cannot read raw SQL.')}
      </Banner>
      {state.error && <Banner status="error" onClose={() => dispatch({type: 'dismiss'})}>{state.error}</Banner>}
      {state.status === 'loading' && <Box role="status" sx={{fontSize: '0.75rem'}}>{gettext('Loading access...')}</Box>}
      {state.status === 'error' && <EmptyState message={gettext('The access list is unavailable.')} />}

      {listing && <>
        <Section title={gettext('Add people or roles')}>
          <Stack direction="row" gap="compact" sx={{alignItems: 'flex-start', flexWrap: 'wrap'}}>
            <TextField size="small" label={gettext('Find a user or role')} value={state.search.text}
              onChange={(event) => dispatch({type: 'searchText', text: event.target.value})}
              sx={{minWidth: 220, flex: 1}} />
            <Select size="small" label={gettext('Access')} value={state.level} options={levelOptions()}
              onChange={(level) => dispatch({type: 'level', level})} sx={{minWidth: 140}} />
            <Button intent="primary" loading={state.busy === 'add'} disabled={!canAdd(state)} onClick={add}>
              {gettext('Add')}</Button>
          </Stack>
          {state.pick && <Stack direction="row" gap="compact" sx={{alignItems: 'center'}}>
            <Badge status="info" label={gettext('%s: %s', kindLabel(state.pick.type), state.pick.name)} />
            <Button size="small" onClick={() => dispatch({type: 'pick', principal: null})}>{gettext('Clear')}</Button>
          </Stack>}
          {state.search.status === 'error' && <Banner status="error">{state.search.error}</Banner>}
          {state.search.status === 'loading' && <Box role="status" sx={{fontSize: '0.75rem'}}>{gettext('Searching...')}</Box>}
          {state.search.status === 'ready' && results.length === 0 &&
            <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
              {gettext('Nobody you can see matches. You can only share with people who share a role with you.')}</Box>}
          <PrincipalList label={gettext('Matching users and roles')} items={results}
            onPick={(principal) => dispatch({type: 'pick', principal})} />
        </Section>

        <Section title={gettext('Who has access')}>
          <Box component="ul" aria-label={gettext('Access list')} sx={{m: 0, p: 0, listStyle: 'none'}}>
            <Box component="li" sx={{display: 'flex', gap: 1, alignItems: 'center', py: 0.5, borderBottom: '1px solid',
              borderColor: 'divider'}}>
              <Box sx={{flex: 1}}>
                {listing.owner.is_you ? gettext('You') : (listing.owner.name || gettext('Another user'))}
              </Box>
              <Badge status="success" label={gettext('Owner')} />
            </Box>
            {rows.map((row) => <Box component="li" key={row.key}
              sx={{display: 'flex', gap: 1, alignItems: 'center', py: 0.5, borderBottom: '1px solid',
                borderColor: 'divider', flexWrap: 'wrap'}}>
              <Box sx={{flex: 1, minWidth: 140}}>
                {row.name || gettext('Unknown')}{' '}
                <Box component="span" sx={{fontSize: '0.7rem', color: 'text.secondary'}}>({kindLabel(row.principalType)})</Box>
              </Box>
              {row.kind === 'direct' ? <>
                <Select size="small" label={gettext('Access of %s', row.name)} value={row.level}
                  options={levelOptions()} disabled={busy}
                  onChange={(level) => attempt(`level-${row.grantId}`, () => client.updateGrant(
                    resourceType, resourceId, row.grantId, level))} sx={{minWidth: 130}} />
                <Button size="small" intent="destructive" disabled={busy}
                  aria-label={gettext('Remove access of %s', row.name)}
                  onClick={() => attempt(`remove-${row.grantId}`, () => client.removeGrant(
                    resourceType, resourceId, row.grantId))}>{gettext('Remove')}</Button>
              </> : <>
                <Badge status="neutral" label={row.source ?
                  gettext('%s, inherited from %s', levelName(row.level), row.source) :
                  gettext('%s, inherited', levelName(row.level))} />
              </>}
            </Box>)}
          </Box>
          {rows.length === 0 && <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
            {gettext('Nobody else has access yet.')}</Box>}
        </Section>

        {hasCollection && <Section title={gettext('Inheritance')}>
          <Checkbox size="small" checked={listing.inherit} disabled={busy}
            label={gettext('Inherit access from the containing collection')}
            onChange={(checked) => attempt('inherit', () => client.setInherit(resourceType, resourceId, checked))} />
          <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
            {listing.inherit ?
              gettext('Anyone with access to a containing collection also has it here. Turn this off to keep only the people listed above.') :
              gettext('Access from containing collections is not applied. Only the people listed above and the owner can open this.')}
          </Box>
        </Section>}

        <Section title={gettext('Ownership')}>
          <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
            {gettext('The owner always has full access. Transferring ownership is recorded in the audit trail. ' +
              'You keep edit access afterwards.')}
          </Box>
          <Select size="small" label={gettext('New owner')} value={state.newOwner ? String(state.newOwner.id) : ''}
            options={[{value: '', label: gettext('Choose from the search results above')},
              ...owners.map((item) => ({value: String(item.id), label: item.name}))]}
            onChange={(value) => dispatch({type: 'newOwner', principal: owners.find((item) => String(item.id) === value) || null})} />
          <TextField size="small" label={gettext('Type the name %s to confirm', resourceName)} value={state.confirm}
            disabled={!state.newOwner} onChange={(event) => dispatch({type: 'confirm', text: event.target.value})} />
          <Stack direction="row">
            <Button intent="destructive" loading={state.busy === 'transfer'}
              disabled={!canTransfer(state, resourceName)} onClick={transfer}>
              {gettext('Transfer ownership')}</Button>
          </Stack>
        </Section>
      </>}
    </Box>
  </Dialog>;
}

ShareDialog.propTypes = {
  client: PropTypes.shape({
    listGrants: PropTypes.func.isRequired, addGrant: PropTypes.func.isRequired,
    updateGrant: PropTypes.func.isRequired, removeGrant: PropTypes.func.isRequired,
    setInherit: PropTypes.func.isRequired, transferOwner: PropTypes.func.isRequired,
    searchPrincipals: PropTypes.func.isRequired,
  }).isRequired,
  resourceType: PropTypes.oneOf(['collection', 'question', 'dashboard']).isRequired,
  resourceId: PropTypes.string.isRequired,
  resourceName: PropTypes.string.isRequired,
  hasCollection: PropTypes.bool,
  onClose: PropTypes.func.isRequired,
  onChanged: PropTypes.func,
};
