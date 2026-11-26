/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Why a provider refused a draft (design Decision 22). The server sends, for each reason, the field
 * it is about, a registered code and, when the engine's refusal catalog has text for the code, that
 * text; plus an opaque reference to the full reason, which only those allowed to may read. Nothing
 * here is taken from the provider's own message.
 */

import gettext from 'sources/gettext';

/** The refusal a failed request carried (makePost keeps the response data on the error), or null. */
export function refusalOf(error) {
  const refusal = error?.data?.refusal;
  return refusal && typeof refusal === 'object' && Array.isArray(refusal.errors) ? refusal : null;
}

/** The sentence to show for a refusal: the catalog text for each reason, else the generic sentence the
 *  server sent, followed by the reference when there is one. */
export function refusalMessage(refusal, generic) {
  const reasons = (refusal?.errors || []).map((entry) => entry?.message)
    .filter((text) => typeof text === 'string' && text).map((text) => gettext(text));
  const text = reasons.length ? [...new Set(reasons)].join(' ') : generic;
  return refusal?.reference ? `${text} ${gettext('Reference: %s', refusal.reference)}` : text;
}

/** {field id: text} for the reasons that name a field and have text. */
export function refusalFieldErrors(error) {
  const fields = {};
  for(const entry of refusalOf(error)?.errors || []) {
    if(entry?.field_id && typeof entry.message === 'string' && entry.message && !fields[entry.field_id]) {
      fields[entry.field_id] = gettext(entry.message);
    }
  }
  return fields;
}
