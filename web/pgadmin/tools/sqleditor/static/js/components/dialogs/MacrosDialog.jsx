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
import RecordGrid from '../../../../../../static/js/cdeadmin_ui/objects/RecordGrid';
import {QueryToolContext, getRandomName} from '../QueryToolComponent';

function computeChangedMacros(initialMacros, currentMacros) {
  const changed = [];
  const currentByOrigId = new Map();

  for (const row of currentMacros) {
    const mid = row.mid !== '' && row.mid != null ? Number(row.mid) : undefined;
    if (row._origId != null) {
      currentByOrigId.set(row._origId, row);
      const orig = initialMacros.find((m) => m.id === row._origId);
      if (
        !orig ||
        orig.name !== row.name ||
        orig.sql !== row.sql ||
        Number(orig.id) !== Number(mid ?? orig.id)
      ) {
        changed.push({
          id: row._origId,
          ...(mid !== undefined ? {mid} : {}),
          name: row.name,
          sql: row.sql,
        });
      }
    } else {
      changed.push({
        ...(mid !== undefined ? {mid} : {}),
        name: row.name,
        sql: row.sql,
      });
    }
  }

  for (const orig of initialMacros) {
    if (!currentByOrigId.has(orig.id)) {
      changed.push({id: orig.id, name: null, sql: null});
    }
  }

  return changed;
}

export default function MacrosDialog({onClose, onSave}) {
  const queryToolCtx = useContext(QueryToolContext);
  const [macrosData, setMacrosData] = useState([]);
  const [initialMacros, setInitialMacros] = useState([]);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    const fetchMacrosData = async () => {
      setLoading(true);
      setError('');
      try {
        const {data: userMacroRespData} = await queryToolCtx.api.get(
          url_for('sqleditor.get_user_macros')
        );
        const {data: respData} = await queryToolCtx.api.get(
          url_for('sqleditor.get_macros', {
            trans_id: queryToolCtx.params.trans_id,
          })
        );
        if (!active) return;
        const activeUserMacros = (userMacroRespData || []).filter((m) =>
          Boolean(m.name)
        );
        setInitialMacros(activeUserMacros);
        setMacrosData((respData?.macro || []).map((m) => ({...m, mid: m.id})));
        setRows(
          activeUserMacros.map((m) => ({
            _origId: m.id,
            mid: m.id != null ? String(m.id) : '',
            name: m.name || '',
            sql: m.sql || '',
          }))
        );
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
    fetchMacrosData();
    return () => {
      active = false;
    };
  }, [queryToolCtx]);

  const keyOptions = useMemo(
    () => [
      {label: '', value: ''},
      ...macrosData.map((m) => ({
        label: m.key_label,
        value: String(m.id),
      })),
    ],
    [macrosData]
  );

  const macroField = useMemo(
    () => ({
      field_id: 'macro',
      label: gettext('Macros'),
      columns: [
        {
          field_id: 'mid',
          label: gettext('Key'),
          control: 'select',
          options: keyOptions,
          default: '',
        },
        {
          field_id: 'name',
          label: gettext('Name'),
          control: 'text',
          default: '',
        },
        {
          field_id: 'sql',
          label: gettext('SQL'),
          control: 'code',
          language: 'sql',
          default: '',
        },
      ],
    }),
    [keyOptions]
  );

  const validationError = useMemo(() => {
    const keys = rows
      .map((m) => (m.mid !== '' && m.mid != null ? String(m.mid) : null))
      .filter(Boolean);
    if (keys.length !== new Set(keys).size) {
      return gettext('Key must be unique.');
    }
    const names = rows.map((m) => String(m.name || '').trim().toLowerCase());
    if (names.some((n) => !n)) {
      return gettext('Name cannot be empty.');
    }
    if (names.length !== new Set(names).size) {
      return gettext('Name must be unique.');
    }
    if (rows.some((m) => !String(m.sql || '').trim())) {
      return gettext('SQL cannot be empty.');
    }
    return '';
  }, [rows]);

  const changedPayload = useMemo(
    () => computeChangedMacros(initialMacros, rows),
    [initialMacros, rows]
  );

  const handleRowsChange = (nextRows) => {
    const existingNames = rows.map((m) => m.name).filter(Boolean);
    setRows(
      nextRows.map((r) => {
        if (!r._origId && !r.name && !r._namedOnce) {
          const generated = getRandomName ? getRandomName(existingNames) : '';
          if (generated) existingNames.push(generated);
          return {...r, name: generated || '', _namedOnce: true};
        }
        return r;
      })
    );
  };

  const handleSave = async () => {
    if (validationError || saving || loading) return;
    setSaving(true);
    setError('');
    try {
      const {data: respData} = await queryToolCtx.api.put(
        url_for('sqleditor.set_macros', {
          trans_id: queryToolCtx.params.trans_id,
        }),
        {changed: changedPayload}
      );
      onSave?.((respData || []).filter((m) => Boolean(m.name)));
      onClose?.();
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

  if (!loading && macrosData.length === 0 && !error) {
    return null;
  }

  return (
    <ModalContent className="MacrosDialog-root">
      <Box style={{flexGrow: 1, padding: 12, overflow: 'auto'}}>
        <Stack spacing={1.5}>
          {error && <Banner tone="error">{error}</Banner>}
          <RecordGrid
            field={macroField}
            rows={rows}
            onChange={handleRowsChange}
            disabled={loading || saving}
            error={validationError}
            defaultPresentation="hybrid"
            addLabel={gettext('Add macro')}
            emptyText={gettext('No macros defined.')}
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
          disabled={
            loading ||
            saving ||
            changedPayload.length === 0 ||
            Boolean(validationError)
          }
          onClick={handleSave}
        >
          {gettext('Save')}
        </Button>
      </ModalFooter>
    </ModalContent>
  );
}

MacrosDialog.propTypes = {
  onClose: PropTypes.func,
  onSave: PropTypes.func,
};
