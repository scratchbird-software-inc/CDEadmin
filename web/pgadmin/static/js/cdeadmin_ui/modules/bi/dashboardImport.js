/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Reading a monitoring dashboard for bi_dashboard_from_ddn
 * (web/pgadmin/cdeadmin/bi/dashboard_ddn.py). The converter takes a
 * ddn-source-workspace@1 snapshot: {format, entry, files: {path: text}}.
 * A person provides either the saved snapshot (a .json file) or the
 * dashboard.ddn source itself, which is wrapped as a one-file snapshot. The
 * server decides whether it is a monitoring dashboard and reports what the
 * conversion cannot represent; nothing here interprets DDN.
 */

import gettext from 'sources/gettext';

export const DDN_FORMAT = 'ddn-source-workspace@1';
export const DDN_ENTRY = 'dashboard.ddn';

const isPlain = (value) => value && typeof value === 'object' && !Array.isArray(value);

/** A snapshot from the text of a chosen file. Throws an Error with a plain message. */
export function snapshotFromText(fileName, text) {
  const body = String(text ?? '');
  if(!body.trim()) throw new Error(gettext('The file is empty.'));
  if(/\.json$/i.test(fileName) || (!/\.ddn$/i.test(fileName) && body.trimStart().startsWith('{'))) {
    let parsed;
    try {
      parsed = JSON.parse(body);
    } catch {
      throw new Error(gettext('The file is not a valid DDN snapshot.'));
    }
    if(!isPlain(parsed) || !isPlain(parsed.files)) throw new Error(gettext('The file is not a DDN snapshot.'));
    return parsed;
  }
  return {format: DDN_FORMAT, entry: DDN_ENTRY, files: {[DDN_ENTRY]: body}};
}

/** Text of a File, with a FileReader fallback for older runtimes. */
export function readFileText(file) {
  if(typeof file.text === 'function') return file.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error(gettext('The file could not be read.')));
    reader.readAsText(file);
  });
}

/** Loss entries ({code, severity, detail}) as lines for a report. */
export function lossLines(loss) {
  return (loss || []).map((item) => ({
    severity: item.severity === 'error' ? 'error' : 'warning',
    text: item.detail || item.code,
  }));
}
