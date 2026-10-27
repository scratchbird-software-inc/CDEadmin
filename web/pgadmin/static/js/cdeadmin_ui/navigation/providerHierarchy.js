/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/** Keep provider ownership levels visible and free of connection side effects. */
export function allowsSoleChildAutomation(itemData) {
  // A connector group can contain an unconnected legacy PostgreSQL server.
  // Opening that group must not start SQL authentication merely because it has
  // one child: native backup/replication administration can use another native
  // admission path. Explicit server expansion keeps its normal behavior.
  return itemData?.cde_endpoint !== true && itemData?._type !== 'engine_type';
}
