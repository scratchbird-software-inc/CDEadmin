import {useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {useLocaleRevision} from '../actions/t_actions';
import {Button} from '../primitives/Button';
import {ScratchScrollArea} from '../base/ScratchScrollArea';
import UnifiedDataGrid from '../data/UnifiedDataGrid';
import ColumnOrderDialog from './RecordColumnOrderDialog';
import {formatRowsForExport} from './dataEditSurfaceHelpers';

const informationColumns = ['name', 'native_type', 'client_type', 'nullable', 'key_role', 'comment']
  .map((name) => ({name}));
const informationColumnNames = informationColumns.map(({name}) => name);

export default function SurfaceInformation({fields, sql, effectiveQuery, filters = [], sorts = [], onSave}) {
  const localeRevision = useLocaleRevision();
  const [selection, setSelection] = useState(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const attributes = useMemo(() => [
    ['name', gettext('Field Name')],
    ['native_type', gettext('Server Native Type')],
    ['client_type', gettext('Client Type')],
    ['nullable', gettext('Nullable')],
    ['key_role', gettext('Key')],
    ['comment', gettext('Comment')],
  ], [localeRevision]);
  const labels = Object.fromEntries(attributes);
  const columns = (selection?.order || informationColumnNames).filter((name) =>
    !selection || selection.visible.includes(name)
  );
  const values = fields.map((field) => Object.fromEntries(columns.map((name) => [
    labels[name], field[name] ?? '',
  ])));
  const copy = async (format) => {
    try {
      const text = format === 'text'
        ? [columns.map((name) => labels[name]).join(' | '), ...values.map((row) =>
          columns.map((name) => row[labels[name]]).join(' | ')
        )].join('\n')
        : formatRowsForExport(values.map((row) => ({values: row})),
          columns.map((name) => ({name: labels[name]})), format);
      await navigator.clipboard.writeText(text);
      setCopyError(false);
    } catch {
      setCopyError(true);
    }
  };

  return (
    <ScratchScrollArea orientation="both" fillViewport style={{flex: 1, minHeight: 0}}>
      <div style={{padding: 12}}>
        {fields.length > 0 ? (
          <>
            <div style={{display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8}}>
              <Button onClick={() => setPickerOpen(true)}>{gettext('Columns…')}</Button>
              <Button onClick={() => copy('csv')}>{gettext('Copy CSV')}</Button>
              <Button onClick={() => copy('tsv')}>{gettext('Copy TSV')}</Button>
              <Button onClick={() => copy('text')}>{gettext('Copy Plain Text')}</Button>
            </div>
            {copyError && <p role="alert">{gettext('Could not copy to clipboard.')}</p>}
            <UnifiedDataGrid
              ariaLabel={gettext('Object field information')}
              qaKey="surface-information-grid"
              columns={columns.map((name) => ({name, label: labels[name]}))}
              rows={fields}
              readOnly
              searchable
              minHeight={220}
            />
            <ColumnOrderDialog
              open={pickerOpen}
              scope="grid"
              allColumns={informationColumns}
              columnLabels={labels}
              visibleNames={selection?.visible || informationColumnNames}
              orderNames={selection?.order || informationColumnNames}
              onClose={() => setPickerOpen(false)}
              onApply={(order, visible) => {
                setSelection({visible, order});
                setPickerOpen(false);
              }}
            />
          </>
        ) : (
          <>
            {effectiveQuery?.sql || sql ? (
              <pre style={{whiteSpace: 'pre-wrap'}}>{effectiveQuery?.sql || sql}</pre>
            ) : (
              <p role="status">{gettext(effectiveQuery?.reason || 'Run a SELECT statement to generate SQL.')}</p>
            )}
            {effectiveQuery?.native_comparison && (
              <p>{gettext('The generated query uses database collation and type conversion rules.')}</p>
            )}
            {effectiveQuery?.buffer_limited && (
              <p>{gettext('The grid contains only buffered rows. The generated query applies the adjustments to the complete result.')}</p>
            )}
            {filters.length > 0 && (
              <section>
                <h3>{gettext('Result Filters')}</h3>
                <ul>{filters.map((filter, index) => (
                  <li key={index}>{[filter.column, filter.op, filter.value].filter((item) => item != null).join(' ')}</li>
                ))}</ul>
              </section>
            )}
            {sorts.length > 0 && (
              <section>
                <h3>{gettext('Result Sorting')}</h3>
                <ol>{sorts.map((sort, index) => (
                  <li key={index}>{sort.column} {String(sort.dir || sort.direction || 'asc').toUpperCase()}</li>
                ))}</ol>
              </section>
            )}
            {onSave && <Button onClick={onSave}>{gettext('Save Query and Layout…')}</Button>}
          </>
        )}
      </div>
    </ScratchScrollArea>
  );
}

SurfaceInformation.propTypes = {
  fields: PropTypes.array.isRequired,
  sql: PropTypes.string,
  effectiveQuery: PropTypes.object,
  sorts: PropTypes.array,
  filters: PropTypes.array,
  onSave: PropTypes.func,
};
