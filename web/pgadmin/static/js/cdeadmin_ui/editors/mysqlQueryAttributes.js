import gettext from 'sources/gettext';

export function mysqlQueryAttributes(source) {
  try {
    const value=JSON.parse(source || '{}');
    if (value && typeof value==='object' && !Array.isArray(value)) return value;
  } catch { /* Report a bounded error without echoing attribute values. */ }
  throw new Error(gettext('MySQL query attributes require a JSON object of names and values.'));
}
