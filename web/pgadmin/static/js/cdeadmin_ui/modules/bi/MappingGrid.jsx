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
import {Select} from '../../primitives/Choice';
import {ComboBox} from '../../primitives/AdvancedControls';
import {Banner} from '../../feedback/Indicators';
import {cardLabel} from './dashboardState';
import {mappingRows} from './dashboardMapping';

const NONE = '__none__';

const kindOf = (target) => target.parameter_id !== undefined ? 'parameter' : 'field';

/** A blank mapping of the chosen kind, pre-filled when the pinned question offers an obvious choice. */
export function blankTarget(kind, cardId, filter, info) {
  if(kind === 'parameter') {
    const compatible = (info?.parameters || []).find((parameter) => parameter.type === filter.type ||
      (parameter.type === 'array' && (filter.multiple || filter.operator === 'between')));
    return {card_id: cardId, parameter_id: compatible?.id || ''};
  }
  if(info?.kind === 'semantic') {
    const first = info.fields[0];
    return {card_id: cardId, field: {source_id: first?.source_id || '', field: first?.field || ''}};
  }
  return {card_id: cardId, field: {column: info?.columns[0] || ''}};
}

function TargetPicker({target, info, label, onChange}) {
  const cardId = target.card_id;
  if(kindOf(target) === 'parameter') {
    if(!info) {
      return <TextField size="small" label={gettext('Parameter for %s', label)} value={target.parameter_id}
        onChange={(event) => onChange({card_id: cardId, parameter_id: event.target.value})} />;
    }
    const options = info.parameters.map((parameter) => ({
      value: parameter.id, label: gettext('%s (%s)', parameter.id, parameter.type)}));
    if(target.parameter_id && !info.parameters.some((parameter) => parameter.id === target.parameter_id)) {
      options.push({value: target.parameter_id, label: gettext('%s (not declared)', target.parameter_id)});
    }
    return <Select size="small" label={gettext('Parameter for %s', label)} value={target.parameter_id}
      options={[{value: '', label: gettext('Choose a parameter')}, ...options]}
      onChange={(parameterId) => onChange({card_id: cardId, parameter_id: parameterId})} />;
  }
  const field = target.field || {};
  if(info?.kind === 'semantic') {
    const options = info.fields.map((item) => ({
      value: `${item.source_id}\u0000${item.field}`, label: gettext('%s (%s.%s)', item.label, item.source_id, item.field)}));
    const current = field.source_id ? `${field.source_id}\u0000${field.field}` : '';
    if(current && !options.some((option) => option.value === current)) {
      options.push({value: current, label: `${field.source_id}.${field.field}`});
    }
    if(options.length) {
      return <Select size="small" label={gettext('Field for %s', label)} value={current}
        options={[{value: '', label: gettext('Choose a field')}, ...options]}
        onChange={(value) => {
          const [sourceId, name] = value.split('\u0000');
          onChange({card_id: cardId, field: {source_id: sourceId || '', field: name || ''}});
        }} />;
    }
    return <Stack direction="row" gap="compact">
      <TextField size="small" label={gettext('Source of %s', label)} value={field.source_id || ''}
        onChange={(event) => onChange({card_id: cardId, field: {source_id: event.target.value, field: field.field || ''}})} />
      <TextField size="small" label={gettext('Field of %s', label)} value={field.field || ''}
        onChange={(event) => onChange({card_id: cardId, field: {source_id: field.source_id || '', field: event.target.value}})} />
    </Stack>;
  }
  return <ComboBox freeEntry size="small" label={gettext('Column for %s', label)} options={info?.columns || []}
    value={field.column || ''} onChange={(column) => onChange({card_id: cardId, field: {column: column || ''}})}
    disableClearable />;
}

TargetPicker.propTypes = {
  target: PropTypes.object.isRequired, info: PropTypes.object,
  label: PropTypes.string.isRequired, onChange: PropTypes.func.isRequired,
};

/**
 * Where one dashboard filter applies: a row per question card, each with
 * zero or more mappings to a parameter or a field of the pinned question.
 * Cards the filter does not reach are listed and flagged.
 */
export default function MappingGrid({state, filter, infos, dispatch}) {
  const rows = mappingRows(state, filter, infos);
  const tabName = (id) => state.tabs.find((tab) => tab.id === id)?.name || id;
  const unmapped = rows.filter((row) => row.unmapped);
  if(!rows.length) {
    return <Banner status="info">{gettext('Add a question card before mapping this filter.')}</Banner>;
  }
  return <Box data-cdeadmin-qa-key="bi.dashboard.mapping" sx={{display: 'grid', gap: 1, minWidth: 0}}>
    {unmapped.length > 0 && <Banner status="warning">
      {filter.targets.length === 0 ?
        gettext('This filter is not mapped to any card.') :
        gettext('Not filtered by %s: %s', filter.name, unmapped.map((row) => cardLabel(row.card)).join(', '))}
    </Banner>}
    <Box component="table" aria-label={gettext('Mapping of %s to cards', filter.name)}
      sx={{width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem',
        '& th, & td': {textAlign: 'left', verticalAlign: 'top', p: 0.5, borderBottom: '1px solid', borderColor: 'divider'}}}>
      <thead>
        <tr><th scope="col">{gettext('Card')}</th><th scope="col">{gettext('Applies to')}</th></tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const label = cardLabel(row.card);
          const lines = row.unmapped ? [{target: null, position: 0, issue: ''}] : row.targets;
          return <tr key={row.card.id}>
            <th scope="row">
              <div>{label}</div>
              <Box sx={{fontWeight: 400, fontSize: '0.7rem', color: 'text.secondary'}}>
                {gettext('%s, %s', tabName(row.card.tab_id), row.info?.name || gettext('loading...'))}
              </Box>
            </th>
            <td>
              {lines.map((line) => {
                const kinds = [{value: NONE, label: gettext('Not mapped')},
                  {value: 'parameter', label: gettext('A parameter')}];
                if(row.info?.kind !== 'sql') kinds.push({value: 'field', label: gettext('A field')});
                const current = line.target ? kindOf(line.target) : NONE;
                return <Box key={line.position} role="group" aria-label={gettext('Mapping of %s on %s', filter.name, label)}
                  sx={{display: 'grid', gap: 0.5, mb: 1, gridTemplateColumns: 'minmax(110px, 0.6fr) minmax(0, 1fr) auto', alignItems: 'start'}}>
                  <Select size="small" label={gettext('Maps %s on %s to', filter.name, label)} value={current}
                    options={kinds}
                    onChange={(kind) => {
                      if(kind === NONE) {
                        if(line.target) dispatch({type: 'removeTarget', filterId: filter.id, cardId: row.card.id, index: line.position});
                        return;
                      }
                      const target = blankTarget(kind, row.card.id, filter, row.info);
                      dispatch(line.target ?
                        {type: 'updateTarget', filterId: filter.id, index: line.position, target} :
                        {type: 'addTarget', filterId: filter.id, target});
                    }} />
                  {line.target ?
                    <TargetPicker target={line.target} info={row.info} label={label}
                      onChange={(target) => dispatch({type: 'updateTarget', filterId: filter.id,
                        index: line.position, target})} /> : <span />}
                  {line.target && <Button size="small" aria-label={gettext('Remove mapping of %s on %s', filter.name, label)}
                    onClick={() => dispatch({type: 'removeTarget', filterId: filter.id, cardId: row.card.id, index: line.position})}>
                    {gettext('Remove')}</Button>}
                  {line.issue && <Box role="alert" sx={{gridColumn: '1 / -1', color: 'error.main', fontSize: '0.75rem'}}>
                    {line.issue}</Box>}
                </Box>;
              })}
              {!row.unmapped && row.info?.kind !== 'sql' && <Button size="small"
                aria-label={gettext('Add another mapping of %s on %s', filter.name, label)}
                onClick={() => dispatch({type: 'addTarget', filterId: filter.id,
                  target: blankTarget('field', row.card.id, filter, row.info)})}>{gettext('Add mapping')}</Button>}
            </td>
          </tr>;
        })}
      </tbody>
    </Box>
  </Box>;
}

MappingGrid.propTypes = {
  state: PropTypes.object.isRequired, filter: PropTypes.object.isRequired,
  infos: PropTypes.object.isRequired, dispatch: PropTypes.func.isRequired,
};
