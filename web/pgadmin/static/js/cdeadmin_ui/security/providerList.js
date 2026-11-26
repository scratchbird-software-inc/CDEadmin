/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

const PAGE_LIMIT = 200;

/**
 * Every resource the endpoint lists. Unlike the editors' catalog loader this
 * does not hide a failure: an account that cannot list principals must see
 * that, not an empty list that reads as "there are none".
 */
export async function listResources(post) {
  const items = [];
  let request = {};
  for(let page = 0; page < PAGE_LIMIT; page++) {
    const result = await post({action: 'resource_page', request});
    items.push(...(result?.items || []));
    if(!result?.next_cursor) break;
    request = {continuation: result.next_cursor, generation: result.generation};
  }
  return items;
}

/**
 * The endpoint URL for one database: the server only accepts a request whose body names the same
 * database as the URL's `database_target_id`, so the manager's own (server-scope) URL cannot be reused.
 */
export function scopedEndpointUrl(endpointUrl, targetId) {
  const [path, query = ''] = String(endpointUrl).split('?');
  const kept = query.split('&').filter((part) => part && !part.startsWith('database_target_id='));
  return `${path}?${[...kept, `database_target_id=${encodeURIComponent(targetId)}`].join('&')}`;
}
