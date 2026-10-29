/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * The signed-embedding actions (docs/en_US/bi_embedding.rst, "Management
 * actions") as methods biClient.js mixes into the one BI client. `call` is the
 * same unwrapping post the other BI methods use. Creating or rotating returns
 * `{embed, secret}`; the secret is shown once and is never stored by the UI.
 */

const withId = (embedId, extra = {}) => ({embed_id: embedId, ...extra});

export function createEmbedClient(call) {
  return {
    embedCatalog: () => call('bi_embed_catalog'),
    listEmbeds: async (type, id) => (await call('bi_embed_list', {resource_type: type, resource_id: id})).items || [],
    getEmbed: (embedId) => call('bi_embed_get', withId(embedId)),
    createEmbed: (embed) => call('bi_embed_create', {embed}),
    updateEmbed: (embedId, expectedRevision, embed) => call('bi_embed_update', withId(embedId, {
      expected_revision: expectedRevision, embed})),
    enableEmbed: (embedId, delegationDays) => call('bi_embed_enable', withId(embedId,
      delegationDays ? {delegation_days: delegationDays} : {})),
    disableEmbed: (embedId) => call('bi_embed_disable', withId(embedId)),
    revokeEmbed: (embedId) => call('bi_embed_revoke', withId(embedId)),
    deleteEmbed: (embedId) => call('bi_embed_delete', withId(embedId)),
    rotateEmbedKey: (embedId) => call('bi_embed_rotate', withId(embedId)),
    retireEmbedKey: (embedId) => call('bi_embed_retire_key', withId(embedId)),
    /** A token for testing, signed server-side with the current key. */
    mintEmbedToken: (embedId, {params, claims, ttlSeconds} = {}) => call('bi_embed_mint', withId(embedId, {
      ...(params && Object.keys(params).length ? {params} : {}),
      ...(claims && Object.keys(claims).length ? {claims} : {}),
      ...(ttlSeconds ? {ttl_seconds: ttlSeconds} : {}),
    })),
    /** A short-lived one-time token the BI UI may frame itself. */
    previewEmbed: (embedId, {params, claims} = {}) => call('bi_embed_preview', withId(embedId, {
      ...(params && Object.keys(params).length ? {params} : {}),
      ...(claims && Object.keys(claims).length ? {claims} : {}),
    })),
    checkEmbedToken: (embedId, token) => call('bi_embed_check_token', withId(embedId, {token})),
    embedStats: (embedId, days = 30) => call('bi_embed_stats', withId(embedId, {days})),
  };
}
