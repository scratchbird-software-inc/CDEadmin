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
import {Select} from '../../primitives/Choice';
import {Banner} from '../../feedback/Indicators';
import Section from './Section';

const TABLE = 'table:';
const MODEL = 'model:';

/** Choose what the question reads: a catalog table or a semantic model. */
export default function SourcePicker({source, sources, models, status, error, onSelectTable, onSelectModel, validation}) {
  const value = source.kind === 'model' ? `${MODEL}${source.model.id}` :
    source.relation.length ? `${TABLE}${source.relation.join('.')}` : '';
  const options = [
    {value: '', label: status === 'loading' ? gettext('Loading sources...') : gettext('Choose a source')},
    ...sources.map((item) => ({value: `${TABLE}${item.label}`, label: gettext('Table: %s', item.label)})),
    ...models.map((item) => ({value: `${MODEL}${item.model_id}`, label: gettext('Model: %s', item.name)})),
  ];
  // A stored question may name a source the lists no longer show; keep it selectable.
  if(value && !options.some((option) => option.value === value)) {
    options.push({value, label: value.startsWith(MODEL) ? gettext('Model: %s', source.model.id) :
      gettext('Table: %s', source.relation.join('.'))});
  }
  const change = (next) => {
    if(next.startsWith(MODEL)) {
      const model = models.find((item) => item.model_id === next.slice(MODEL.length));
      onSelectModel(model.model_id, model.revision);
    } else if(next.startsWith(TABLE)) {
      onSelectTable(sources.find((item) => item.label === next.slice(TABLE.length))?.relation ??
        next.slice(TABLE.length).split('.'));
    }
  };
  return <Section title={gettext('Source')} error={validation} qaKey="bi.builder.source">
    {status === 'error' && <Banner status="error">{error}</Banner>}
    <Select size="small" fullWidth label={gettext('Start from')} value={value} options={options}
      disabled={status === 'loading'} onChange={change} />
  </Section>;
}

SourcePicker.propTypes = {
  source: PropTypes.object.isRequired,
  sources: PropTypes.array.isRequired,
  models: PropTypes.array.isRequired,
  status: PropTypes.string.isRequired,
  error: PropTypes.string,
  validation: PropTypes.string,
  onSelectTable: PropTypes.func.isRequired,
  onSelectModel: PropTypes.func.isRequired,
};
