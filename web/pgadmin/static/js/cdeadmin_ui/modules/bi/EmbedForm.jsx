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
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {Banner} from '../../feedback/Indicators';
import {THEMES, originProblem, warnings} from './embeds';

const MODE_LABELS = {
  off: () => gettext('Not used'),
  locked: () => gettext('Locked (set by the token)'),
  editable: () => gettext('Editable by the viewer'),
  hidden: () => gettext('Hidden (set by the token)'),
};
const THEME_LABELS = {auto: () => gettext('Follow the page'), light: () => gettext('Light'), dark: () => gettext('Dark')};

function Section({title, children}) {
  return <Box component="section" aria-label={title} sx={{display: 'grid', gap: 0.75}}>
    <Box component="h4" sx={{m: 0, fontSize: '0.8125rem'}}>{title}</Box>
    {children}
  </Box>;
}

Section.propTypes = {title: PropTypes.string.isRequired, children: PropTypes.node};

function ParameterTable({draft, dispatch, errors}) {
  if(!draft.parameters.length) {
    return <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
      {draft.resource.type === 'dashboard' ? gettext('This dashboard has no filters.') :
        gettext('This question has no parameters.')}</Box>;
  }
  return <Box component="table" aria-label={gettext('Parameters')} sx={{borderCollapse: 'collapse', fontSize: '0.8125rem'}}>
    <thead>
      <tr>
        <Box component="th" scope="col" sx={{textAlign: 'left', pr: 1}}>{gettext('Parameter')}</Box>
        <Box component="th" scope="col" sx={{textAlign: 'left'}}>{gettext('Who sets it')}</Box>
      </tr>
    </thead>
    <tbody>
      {draft.parameters.map((item) => <tr key={item.id}>
        <Box component="td" sx={{pr: 1, verticalAlign: 'top', py: 0.5}}>
          {item.name}{item.required && <Box component="span" sx={{color: 'text.secondary'}}>{' '}{gettext('(required)')}</Box>}
        </Box>
        <td>
          <Select size="small" label={gettext('Mode of %s', item.name)} value={item.mode}
            options={Object.keys(MODE_LABELS).map((value) => ({value, label: MODE_LABELS[value]()}))}
            validationMessage={errors[`parameter.${item.id}`]} sx={{minWidth: 240}}
            onChange={(mode) => dispatch({type: 'mode', id: item.id, mode})} />
        </td>
      </tr>)}
    </tbody>
  </Box>;
}

ParameterTable.propTypes = {draft: PropTypes.object.isRequired, dispatch: PropTypes.func.isRequired, errors: PropTypes.object.isRequired};

function OriginList({draft, dispatch, errors}) {
  const problem = draft.originText.trim() ? originProblem(draft.originText.trim().replace(/\/+$/, '')) : '';
  return <Box sx={{display: 'grid', gap: 0.5}}>
    <Box component="ul" aria-label={gettext('Allowed origins')} sx={{m: 0, p: 0, listStyle: 'none', display: 'grid', gap: 0.25}}>
      {draft.origins.map((origin, index) => <Box component="li" key={origin} sx={{display: 'flex', gap: 1, alignItems: 'center'}}>
        <Box component="code">{origin}</Box>
        <Button size="small" aria-label={gettext('Remove origin %s', origin)}
          onClick={() => dispatch({type: 'removeOrigin', index})}>{gettext('Remove')}</Button>
        {errors[`origin.${index}`] && <Box role="alert" sx={{fontSize: '0.75rem'}}>{errors[`origin.${index}`]}</Box>}
      </Box>)}
    </Box>
    <Stack direction="row" gap="compact" sx={{alignItems: 'flex-start'}}>
      <TextField size="small" label={gettext('Add an origin')} placeholder="https://app.example.com"
        value={draft.originText} validationMessage={problem} sx={{minWidth: 280}}
        onChange={(event) => dispatch({type: 'originText', value: event.target.value})} />
      <Button disabled={!draft.originText.trim() || Boolean(problem)} onClick={() => dispatch({type: 'addOrigin'})}>
        {gettext('Add origin')}</Button>
    </Stack>
    {errors.origins && <Box role="alert" sx={{fontSize: '0.75rem'}}>{errors.origins}</Box>}
  </Box>;
}

OriginList.propTypes = {draft: PropTypes.object.isRequired, dispatch: PropTypes.func.isRequired, errors: PropTypes.object.isRequired};

function ClaimList({draft, dispatch, errors}) {
  return <Box sx={{display: 'grid', gap: 0.5}}>
    {draft.claims.map((claim, index) => <Stack key={index} direction="row" gap="compact" sx={{alignItems: 'flex-start'}}>
      <TextField size="small" label={gettext('Claim %s', index + 1)} value={claim.name} sx={{minWidth: 200}}
        validationMessage={errors[`claim.${index}`]}
        onChange={(event) => dispatch({type: 'claim', index, patch: {name: event.target.value}})} />
      <Checkbox label={gettext('Required')} checked={claim.required}
        onChange={(required) => dispatch({type: 'claim', index, patch: {required}})} />
      <Button size="small" aria-label={gettext('Remove claim %s', index + 1)}
        onClick={() => dispatch({type: 'removeClaim', index})}>{gettext('Remove')}</Button>
    </Stack>)}
    <Stack direction="row"><Button size="small" onClick={() => dispatch({type: 'addClaim'})}>{gettext('Add a claim')}</Button></Stack>
    {errors.claims && <Box role="alert" sx={{fontSize: '0.75rem'}}>{errors.claims}</Box>}
  </Box>;
}

ClaimList.propTypes = {draft: PropTypes.object.isRequired, dispatch: PropTypes.func.isRequired, errors: PropTypes.object.isRequired};

const bind = (dispatch, field) => (event) => dispatch({type: 'field', field, value: event.target.value});

/** The embed definition form; the parent owns validation and saving. */
export default function EmbedForm({draft, dispatch, errors, catalog, rawSql = false}) {
  const notes = warnings(draft, {rawSql});
  return <Box sx={{display: 'grid', gap: 1.25}}>
    <TextField size="small" label={gettext('Name')} value={draft.name} validationMessage={errors.name}
      onChange={(event) => dispatch({type: 'field', field: 'name', value: event.target.value})} />
    <Section title={gettext('Parameters')}>
      <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
        {gettext('Locked and hidden values come only from the signed token. A viewer can change only editable ones.')}
      </Box>
      <ParameterTable draft={draft} dispatch={dispatch} errors={errors} />
    </Section>
    <Section title={gettext('Claims')}>
      <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
        {gettext('Claims are signed values such as a tenant id. Semantic row policies read them; nothing else does.')}
      </Box>
      <ClaimList draft={draft} dispatch={dispatch} errors={errors} />
    </Section>
    <Section title={gettext('Sites that may show this embed')}>
      <OriginList draft={draft} dispatch={dispatch} errors={errors} />
    </Section>
    <Section title={gettext('Tokens')}>
      <Stack direction="row" gap="compact" sx={{flexWrap: 'wrap', alignItems: 'flex-start'}}>
        <TextField size="small" label={gettext('Longest token lifetime (seconds)')} value={draft.lifetime}
          validationMessage={errors.lifetime} sx={{width: 220}} onChange={bind(dispatch, 'lifetime')} />
        <TextField size="small" label={gettext('Embed expires at (optional)')} value={draft.expiresAt}
          placeholder="2027-01-31T00:00:00Z" sx={{width: 240}} onChange={bind(dispatch, 'expiresAt')} />
      </Stack>
      <Checkbox label={gettext('Tokens are one-time (each needs a unique id)')} checked={draft.requireJti}
        onChange={(value) => dispatch({type: 'field', field: 'requireJti', value})} />
    </Section>
    <Section title={gettext('Display and limits')}>
      <Stack direction="row" gap="compact" sx={{flexWrap: 'wrap', alignItems: 'flex-start'}}>
        <Select size="small" label={gettext('Theme')} value={draft.display.theme} sx={{minWidth: 160}}
          options={THEMES.map((value) => ({value, label: THEME_LABELS[value]()}))}
          onChange={(theme) => dispatch({type: 'display', patch: {theme}})} />
        <TextField size="small" label={gettext('Rows per page')} value={draft.pageSize}
          validationMessage={errors.pageSize} sx={{width: 130}} onChange={bind(dispatch, 'pageSize')} />
        <TextField size="small" label={gettext('Most rows shown')} value={draft.maxRows}
          validationMessage={errors.maxRows} sx={{width: 130}} onChange={bind(dispatch, 'maxRows')} />
      </Stack>
      <Stack direction="row" gap="standard" sx={{flexWrap: 'wrap'}}>
        <Checkbox label={gettext('Show the title')} checked={draft.display.title}
          onChange={(title) => dispatch({type: 'display', patch: {title}})} />
        <Checkbox label={gettext('Show a border')} checked={draft.display.border}
          onChange={(border) => dispatch({type: 'display', patch: {border}})} />
        <Checkbox label={gettext('Allow downloads')} checked={draft.display.download}
          disabled={catalog.downloads_allowed === false}
          onChange={(download) => dispatch({type: 'display', patch: {download}})} />
      </Stack>
      {errors.download && <Box role="alert" sx={{fontSize: '0.75rem'}}>{errors.download}</Box>}
    </Section>
    {notes.map((note) => <Banner key={note} status="warning">{note}</Banner>)}
  </Box>;
}

EmbedForm.propTypes = {
  draft: PropTypes.object.isRequired, dispatch: PropTypes.func.isRequired, errors: PropTypes.object.isRequired,
  catalog: PropTypes.object.isRequired, rawSql: PropTypes.bool,
};
