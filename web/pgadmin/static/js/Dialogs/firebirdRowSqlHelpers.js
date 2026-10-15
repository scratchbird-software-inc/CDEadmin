/* global BigInt */
export function identifier(name, dialect=3) {
  if (typeof name !== 'string' || !name || name.includes('\0')) throw new Error('Invalid native identifier.');
  if(dialect === 1) {
    if(!/^[A-Z_][A-Z0-9_$]{0,62}$/.test(name)) throw new Error('Dialect 1 requires exact uppercase unquoted identifiers.');
    return name;
  }
  if(![2,3].includes(dialect)) throw new Error('Unsupported native SQL dialect.');
  return '"' + name.replaceAll('"', '""') + '"';
}
const quoted = value => '\'' + value.replaceAll('\'', '\'\'') + '\'';
export function firebirdLiteral(value, column) {
  if (value === null) return 'NULL';
  const kind = column.input_kind;
  if (kind === 'text') {
    if (typeof value !== 'string' || value.includes('\0') || new TextEncoder().encode(value).length > 16000) throw new Error('Use parameters for this text value.');
    return quoted(value);
  }
  if (['integer', 'decimal', 'decfloat', 'float32', 'float64'].includes(kind)) {
    const text = typeof value === 'object' ? value.data : String(value);
    const special = /^[+-]?(?:s?NaN|Inf(?:inity)?)$/i.test(text);
    if (!(kind === 'integer' ? /^[+-]?\d+$/.test(text) : special || /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(text))) throw new Error('Invalid numeric representation.');
    if (typeof value === 'number' && !Number.isSafeInteger(value)) throw new Error('Use an exact text numeric representation.');
    if (['decfloat', 'float32', 'float64'].includes(kind)) {
      const type = {decfloat: 'DECFLOAT(34)', float32: 'FLOAT', float64: 'DOUBLE PRECISION'}[kind];
      if (!type) throw new Error('Unsupported special numeric value.');
      return `CAST(${quoted(text)} AS ${type})`;
    }
    if (special || (kind === 'decimal' && /e/i.test(text))) throw new Error('Use parameters for special or exponent-form exact decimals.');
    return text;
  }
  if (kind === 'boolean' && typeof value === 'boolean') return value ? 'TRUE' : 'FALSE';
  if (['date', 'time', 'timestamp'].includes(kind)) {
    const day = '\\d{4}-\\d{2}-\\d{2}', clock = '\\d{2}:\\d{2}:\\d{2}(?:\\.\\d{1,4})?';
    if (typeof value !== 'string' || !new RegExp('^' + (kind === 'date' ? day : kind === 'time' ? clock : day + '[ T]' + clock) + '$').test(value)) throw new Error('Invalid temporal representation.');
    return `${kind.toUpperCase()} ${quoted(value)}`;
  }
  if (kind === 'binary' && value?.encoding === 'base64') {
    const raw = atob(value.data);
    if (btoa(raw) !== value.data || raw.length !== value.byte_length) throw new Error('Invalid binary envelope.');
    if (raw.length > 16000) throw new Error('Use parameters for this binary value.');
    return 'x\'' + Array.from(raw, char => char.charCodeAt(0).toString(16).padStart(2, '0')).join('') + '\'';
  }
  throw new Error('This native value requires bound parameters; select parameter output.');
}

export function generateRowSql({table, columns, rows, operation, keys=[], inColumn, inline=false, dialect=3}) {
  if (!Array.isArray(rows) || !rows.length || rows.length > 100) throw new Error('Select 1–100 rows from this page.');
  if(!Array.isArray(columns) || !columns.length || columns.length > 2048) throw new Error('Native columns are required.');
  const quote = name => identifier(name, dialect);
  quote(table);
  const names = columns.map(column => column.name);
  if (new Set(names).size !== names.length) throw new Error('Ambiguous native column names.');
  if (!['insert', 'update', 'upsert', 'in'].includes(operation)) throw new Error('Unknown SQL generation operation.');
  if (['update', 'upsert'].includes(operation) && (!keys.length || new Set(keys).size !== keys.length || keys.some(name => !names.includes(name)))) throw new Error('Select explicit matching columns.');
  if (operation === 'in' && !names.includes(inColumn)) throw new Error('Select an IN-list column.');
  const needed = operation === 'in' ? [inColumn] : operation === 'update' ? [...keys, ...columns.filter(column => column.editable !== false && !keys.includes(column.name)).map(column => column.name)] : columns.filter(column => column.insertable !== false).map(column => column.name);
  if(rows.some(row => !row?.values || typeof row.values !== 'object' || needed.some(name => !Object.hasOwn(row.values, name)))) throw new Error('Selected rows lack complete native values.');
  const byName = new Map(columns.map(column => [column.name, column]));
  const plans = [];
  const bind = (value, column, parameters) => {
    if (value === undefined) throw new Error('A selected column value is missing.');
    if(column.input_kind === 'integer' && typeof value === 'number' && !Number.isSafeInteger(value)) throw new Error('Use an exact text integer representation.');
    if (inline) {
      if(dialect === 1 && ['integer','decimal','decfloat'].includes(column.input_kind) &&
        !(column.input_kind === 'integer' && /^[+-]?\d+$/.test(String(value)) && BigInt(value)>=-2147483648n && BigInt(value)<=2147483647n))
        throw new Error('Exact numeric literals require dialect 3 or bound parameters.');
      return firebirdLiteral(value, column);
    }
    parameters.push(value); return '?';
  };
  if (operation === 'in') {
    const parameters = [], column = byName.get(inColumn), name = quote(inColumn);
    const nonnull = rows.map(row => row.values[inColumn]).filter(value => value !== null);
    const parts = [];
    if (nonnull.length) parts.push(`${name} IN (${nonnull.map(value => bind(value, column, parameters)).join(', ')})`);
    if (rows.some(row => row.values[inColumn] === null)) parts.push(`${name} IS NULL`);
    plans.push({source: `SELECT * FROM ${quote(table)} WHERE (${parts.join(' OR ')});`, parameters});
  } else {
    const writable = columns.filter(column => operation === 'update' ? column.editable !== false && !keys.includes(column.name) : column.insertable !== false);
    if (!writable.length) throw new Error('No admitted writable columns for this operation.');
    if (operation === 'upsert' && keys.some(name => !writable.some(column => column.name === name))) throw new Error('Matching columns must be insertable.');
    for (const row of rows) {
      const parameters = [];
      let source;
      if (operation === 'update') {
        const assignments = writable.map(column => `${quote(column.name)} = ${bind(row.values[column.name], column, parameters)}`);
        const predicates = keys.map(name => `${quote(name)} IS NOT DISTINCT FROM ${bind(row.values[name], byName.get(name), parameters)}`);
        source = `UPDATE ${quote(table)} SET ${assignments.join(', ')} WHERE ${predicates.join(' AND ')};`;
      } else {
        source = `${operation === 'upsert' ? 'UPDATE OR INSERT' : 'INSERT'} INTO ${quote(table)} (${writable.map(column => quote(column.name)).join(', ')}) VALUES (${writable.map(column => bind(row.values[column.name], column, parameters)).join(', ')})`;
        if (operation === 'upsert') source += ` MATCHING (${keys.map(name => quote(name)).join(', ')})`;
        source += ';';
      }
      plans.push({source, parameters});
    }
  }
  if (new TextEncoder().encode(JSON.stringify(plans)).length > 1024 * 1024) throw new Error('Generated output exceeds 1 MiB. Select fewer or smaller rows.');
  return plans.map(plan => ({...plan, client_sql_dialect:dialect}));
}
