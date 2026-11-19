import {useEffect, useMemo, useState} from 'react';
import gettext from 'sources/gettext';

export function recordConversionPair(column, pairs) {
  const declared = String(column?.native_type || '').toUpperCase();
  const match = /^(VARBINARY|BINARY)\s*\(\s*(\d+)\s*\)$/.exec(declared);
  const type = match?.[1] || declared;
  const width = [match?.[2], column?.internal_size, column?.max_length]
    .map(Number).find((size) => size > 0);
  if (width != null && width !== 16) return undefined;
  return pairs?.find(({native_types, require_width}) =>
    native_types.includes(type) && (!require_width || width != null)
  );
}

export function useRecordConversions(rows, columns, columnPreferences, pairs, callHost) {
  const selected = useMemo(() => new Map(columns.flatMap((column) => {
    const pair = recordConversionPair(column, pairs);
    return pair && columnPreferences?.[column.name]?.conversionPair === pair.id
      ? [[column.name, pair.id]] : [];
  })), [columns, columnPreferences, pairs]);
  const inputs = useMemo(() => {
    const byPair = new Map();
    for (const [column, pair] of selected) {
      const values = byPair.get(pair) || new Map();
      byPair.set(pair, values);
      for (const row of rows) {
        const value = row.values?.[column];
        if (value?.encoding === 'base64' && value.byte_length === 16) values.set(value.data, value);
      }
    }
    return byPair;
  }, [rows, selected]);

  const [display, setDisplay] = useState(null);
  useEffect(() => {
    if (!inputs.size) return undefined;
    let active = true;
    async function load() {
      const translated = new Map();
      for (const [pair, values] of inputs) {
        const items = [...values.values()];
        const results = new Map();
        translated.set(pair, results);
        for (let offset = 0; offset < items.length && active; offset += 500) {
          const batch = items.slice(offset, offset + 500);
          const response = await callHost('convert_field', {pair, direction: 'display', values: batch});
          batch.forEach((item, index) => results.set(item.data, response.values[index]));
        }
      }
      if (active) setDisplay({inputs, translated});
    }
    load().catch((failure) => {
      if (active) setDisplay({inputs, error: failure?.message || String(failure)});
    });
    return () => { active = false; };
  }, [inputs, callHost]);

  const current = display?.inputs === inputs ? display : null;
  return {
    error: current?.error,
    pairFor: (column) => selected.get(column),
    displayValue(column, value) {
      const pair = selected.get(column);
      return current?.translated?.get(pair)?.get(value?.data) ?? value;
    },
  };
}

export async function convertRecordField(callHost, pairs, preferences, column, value) {
  const available = recordConversionPair(column, pairs);
  const pair = preferences?.[column?.name]?.conversionPair;
  if (typeof value !== 'string' || !available || available.id !== pair) return value;
  const response = await callHost('convert_field', {pair, direction: 'store', values: [value]});
  const converted = response?.values?.[0];
  if (converted?.encoding !== 'base64' || converted.byte_length !== 16) {
    throw new Error(gettext('The provider did not return a UUID binary value.'));
  }
  return converted;
}
