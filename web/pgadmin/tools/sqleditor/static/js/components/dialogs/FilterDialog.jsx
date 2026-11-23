/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useContext, useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import url_for from 'sources/url_for';
import {
  DialogContent as ModalContent,
  DialogFooter as ModalFooter,
} from 'sources/cdeadmin_ui/overlays/DialogLayout';
import {Box, Stack} from '../../../../../../static/js/cdeadmin_ui/primitives/Layout';
import {Button} from '../../../../../../static/js/cdeadmin_ui/primitives/Button';
import {Banner} from '../../../../../../static/js/cdeadmin_ui/feedback/Indicators';
import CodeEditor from '../../../../../../static/js/cdeadmin_ui/editors/CodeEditor';
import RecordGrid from '../../../../../../static/js/cdeadmin_ui/objects/RecordGrid';
import {QueryToolContext} from '../QueryToolComponent';

export default function FilterDialog({onClose, onSave}) {
  const queryToolCtx = useContext(QueryToolContext);
  const [columnOptions, setColumnOptions] = useState([]);
  const [sql, setSql] = useState('');
  const [dataSorting, setDataSorting] = useState([]);
  const [initialSnapshot, setInitialSnapshot] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError('');
      try {
        const {data: respData} = await queryToolCtx.api.get(
          url_for('sqleditor.get_filter_data', {
            trans_id: queryToolCtx.params.trans_id,
          })
        );
        if (!active) return;
        const {column_list: columns, ...filterData} = respData.data.result || {};
        setColumnOptions((columns || []).map((c) => ({label: c, value: c})));
        const initSql = filterData.sql || '';
        const initSort = Array.isArray(filterData.data_sorting)
          ? filterData.data_sorting
          : [];
        setSql(initSql);
        setDataSorting(initSort);
        setInitialSnapshot(JSON.stringify({sql: initSql, data_sorting: initSort}));
      } catch (err) {
        if (active) {
          setError(
            err?.response?.data?.errormsg ||
              err?.message ||
              gettext('Something went wrong')
          );
        }
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    return () => {
      active = false;
    };
  }, [queryToolCtx]);

  const sortingField = useMemo(
    () => ({
      field_id: 'data_sorting',
      label: gettext('Data Sorting'),
      columns: [
        {
          field_id: 'name',
          label: gettext('Column'),
          control: 'select',
          options: columnOptions,
          default: columnOptions[0]?.value || '',
        },
        {
          field_id: 'order',
          label: gettext('Order'),
          control: 'select',
          options: [
            {label: gettext('ASC'), value: 'asc'},
            {label: gettext('DESC'), value: 'desc'},
          ],
          default: 'asc',
        },
        {
          field_id: 'order_null',
          label: gettext('NULLs'),
          control: 'select',
          options: [
            {label: '', value: ''},
            {label: gettext('FIRST'), value: 'nulls first'},
            {label: gettext('LAST'), value: 'nulls last'},
          ],
          default: '',
        },
      ],
    }),
    [columnOptions]
  );

  const validationError = useMemo(() => {
    const names = dataSorting.map((r) => String(r?.name || '').trim());
    if (names.some((n) => !n)) {
      return gettext('Column cannot be empty.');
    }
    if (new Set(names).size !== names.length) {
      return gettext('Column must be unique.');
    }
    return '';
  }, [dataSorting]);

  const isDirty =
    JSON.stringify({sql, data_sorting: dataSorting}) !== initialSnapshot;

  const handleSave = async () => {
    if (validationError || saving || loading) return;
    setSaving(true);
    setError('');
    try {
      const payload = {
        sql: sql || null,
        data_sorting: dataSorting.map((row) => ({
          name: row.name,
          order: row.order || 'asc',
          ...(row.order_null ? {order_null: row.order_null} : {}),
        })),
      };
      const {data: respData} = await queryToolCtx.api.put(
        url_for('sqleditor.set_filter_data', {
          trans_id: queryToolCtx.params.trans_id,
        }),
        payload
      );
      if (respData.data.status) {
        onSave?.();
      } else {
        setError(respData.data.result || gettext('Something went wrong'));
      }
    } catch (err) {
      setError(
        err?.response?.data?.errormsg ||
          err?.message ||
          gettext('Something went wrong')
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalContent>
      <Box style={{flexGrow: 1, padding: 16, overflow: 'auto'}}>
        <Stack spacing={1.5}>
          {error && <Banner tone="error">{error}</Banner>}
          <div>
            <div style={{fontWeight: 600, fontSize: '0.8125rem', marginBottom: 4}}>
              {gettext('SQL Filter')}
            </div>
            <div
              style={{
                height: 120,
                border: '1px solid var(--sr-border, rgba(128,128,128,0.28))',
                borderRadius: 6,
                overflow: 'hidden',
              }}
            >
              {!loading && (
                <CodeEditor
                  label={gettext('SQL Filter')}
                  value={sql}
                  onChange={(val) => setSql(val)}
                  options={{lineWrapping: true}}
                />
              )}
            </div>
          </div>
          <RecordGrid
            field={sortingField}
            rows={dataSorting}
            onChange={setDataSorting}
            disabled={loading || saving}
            error={validationError}
            addLabel={gettext('Add sort column')}
            emptyText={gettext('No sort columns configured.')}
          />
        </Stack>
      </Box>
      <ModalFooter>
        <Button
          data-test="Close"
          disabled={saving}
          onClick={() => onClose?.()}
        >
          {gettext('Cancel')}
        </Button>
        <Button
          data-test="Save"
          variant="primary"
          disabled={loading || saving || !isDirty || Boolean(validationError)}
          onClick={handleSave}
        >
          {gettext('Save')}
        </Button>
      </ModalFooter>
    </ModalContent>
  );
}

FilterDialog.propTypes = {
  onClose: PropTypes.func,
  onSave: PropTypes.func,
};
