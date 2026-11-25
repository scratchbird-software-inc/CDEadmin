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
