/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * "Browse data" source (owner direction 2026-11-05): SELECT every column of a
 * table or view. It is built from the SQL editor's own completion schema, so
 * relation and column names carry the same provider-observed spelling and
 * quoting the editor inserts; this adds no dialect knowledge of its own.
 * Columns the native SELECT * leaves out (hidden from star) are left out.
 *
 * Two schema shapes exist: a flat map whose relation children are an array
 * of completions, and a nested map whose children are entries keyed by name.
 */

function childList(entry) {
  const children = entry?.children;
  if(Array.isArray(children)) return children;
  return Object.values(children || {}).map((child) => child.self);
}

function relationsNamed(schema, name) {
  const found = [];
  const seen = new Set();
  const walk = (branch, parents) => {
    for(const entry of Object.values(branch || {})) {
      if(!entry?.self) continue;
      const path = [...parents, entry];
      if(entry.self.type === 'type' && entry.self.label === name && !seen.has(entry) &&
          childList(entry).some((child) => child?.type === 'property')) {
        seen.add(entry);
        found.push(path);
      }
      if(!Array.isArray(entry.children)) walk(entry.children, path);
    }
  };
  walk(schema, []);
  return found;
}

/**
 * The SELECT statement for one relation, or an `error` saying why there is
 * none. `path` is the relation's display path from the resource inventory;
 * when several schemas hold a relation of that name, the one whose parent
 * names all appear in it is chosen.
 */
export function relationSelectSource(schema, name, path=[], defaultSchema=undefined) {
  if(typeof name !== 'string' || !name) return {error: 'No relation was named.'};
  let candidates = relationsNamed(schema, name);
  if(candidates.length > 1) {
    const qualifiers = new Set(Array.isArray(path) ? path : []);
    const matching = candidates.filter((chain) =>
      chain.slice(0, -1).every((entry) => qualifiers.has(entry.self.label)));
    if(matching.length) {
      // Prefer the most qualified match the path supports.
      const longest = Math.max(...matching.map((chain) => chain.length));
      candidates = matching.filter((chain) => chain.length === longest);
    }
  }
  if(candidates.length > 1 && defaultSchema) {
    // Still undecided: the session's current database or schema, as an
    // unqualified name in the editor would resolve.
    const current = candidates.filter((chain) =>
      chain.slice(0, -1).some((entry) => entry.self.label === defaultSchema));
    if(current.length) candidates = current;
  }
  if(candidates.length === 0) {
    return {error: `The editor metadata lists no columns for ${name}.`};
  }
  if(candidates.length > 1) {
    return {error: `More than one relation is named ${name}; open the SQL editor and qualify it.`};
  }
  const chain = candidates[0];
  const columns = childList(chain.at(-1)).filter((child) =>
    child?.type === 'property' && !child.nativeHiddenFromStar && typeof child.apply === 'string');
  if(columns.length === 0) {
    return {error: `The editor metadata lists no selectable columns for ${name}.`};
  }
  const relation = chain.map((entry) => entry.self.apply).join('.');
  return {source: `SELECT ${columns.map((column) => column.apply).join(', ')}\nFROM ${relation}`};
}
